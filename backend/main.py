"""FastAPI backend for the Campus Customs dashboard.

Start it from the ``backend/`` folder::

    uvicorn main:app --reload --port 8000

Everything this API knows about the shop comes from the campus-customs MCP
server over ``data/campus_customs_new.db``.  The API does not open the database
itself — it calls the same tools the agents call, so the guardrails (human
approval, no negative balances, no double payments) apply to a click in the
dashboard exactly as they apply to an agent.

The division of labour the whole assignment rests on:

* **Agents prepare.** Running a ticket can create ``approvals`` rows, drafts and
  ticket notes.  It can never move money.
* **A human releases.** ``POST /approvals/{id}/approve`` is the only route that
  changes cash, and it records the name of the person who clicked.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import audit
from config import (
    MAX_DELEGATIONS_PER_TICKET,
    MAX_DELEGATION_DEPTH,
    MAX_REQUESTS_BOSS,
    MAX_REQUESTS_SPECIALIST,
    MODEL_NAME,
)
from mcp_tools import call_tool
from runner import work_ticket

app = FastAPI(
    title="Campus Customs Operations",
    description="Backend for the agent dashboard. Agents prepare; humans approve.",
    version="1.0.0",
)

# The dashboard is served from a different port in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# One ticket at a time. Two agent runs at once would race on the same approvals
# and the same balance, and the board would show interleaved nonsense.
_run_lock = asyncio.Lock()


# ------------------------------------------------------------------ shapes


class RunRequest(BaseModel):
    """Optional body for a ticket run."""

    reset_first: bool = Field(
        default=False, description="Reset the shop to its original values before running."
    )


class ApproveRequest(BaseModel):
    """A human releasing (or refusing) one prepared request."""

    decided_by: str = Field(
        min_length=1,
        description="Name of the person deciding. Recorded in payments.approved_by.",
    )
    decision: Literal["approved", "rejected"] = "approved"
    note: str = Field(default="", description="Optional reason, kept with the decision.")


# ------------------------------------------------------------------ routes


@app.get("/", tags=["meta"])
async def index() -> dict:
    """What this API is and which routes it offers."""
    return {
        "service": "Campus Customs Operations",
        "model": MODEL_NAME,
        "shop_date": (await call_tool("get_shop_date"))["shop_today"],
        "rule": "Agents prepare payments; only POST /approvals/{id}/approve moves money.",
        "routes": [
            "GET  /tickets",
            "POST /tickets/{ticket_id}/run",
            "GET  /events",
            "GET  /approvals",
            "POST /approvals/{approval_id}/approve",
            "GET  /cash",
            "POST /reset",
        ],
    }


@app.get("/tickets", tags=["board"])
async def get_tickets() -> dict:
    """Every ticket on the board with its status and what it links to.

    Returns all tickets rather than only open ones, so the dashboard can show a
    ticket moving from open to waiting_approval to resolved without a reload.
    """
    board = await call_tool("list_tickets", {"status": "all"})
    tickets = board["tickets"]
    for ticket in tickets:
        ticket["is_open"] = ticket["status"] == "open"
        ticket["is_resolved"] = ticket["status"] == "resolved"
    return {
        "shop_date": board["shop_today"],
        "count": len(tickets),
        "open_count": sum(1 for t in tickets if t["is_open"]),
        "resolved_count": sum(1 for t in tickets if t["is_resolved"]),
        "tickets": tickets,
    }


@app.post("/tickets/{ticket_id}/run", tags=["board"])
async def run_ticket(ticket_id: int, body: RunRequest | None = None) -> dict:
    """Run the agent team on one ticket and return the Boss's verdict.

    The Boss reads the ticket, delegates to whichever teammates it needs, and
    decides where the ticket lands. Every loop step is appended to the audit
    trail while this runs, so ``GET /events`` shows the work in progress.

    This route can create approval requests. It cannot pay them.
    """
    body = body or RunRequest()
    if _run_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="A ticket run is already in progress. Wait for it to finish.",
        )

    async with _run_lock:
        if body.reset_first:
            await call_tool("reset_shop_database")

        ticket = await call_tool("get_ticket", {"ticket_id": ticket_id})
        if not ticket.get("found"):
            raise HTTPException(status_code=404, detail=f"No ticket {ticket_id}.")

        try:
            verdict, deps = await work_ticket(ticket_id)
        except Exception as exc:  # noqa: BLE001 — surface the failure to the board
            raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc

    return {
        "run_id": deps.run_id,
        "ticket_id": ticket_id,
        "verdict": verdict.model_dump(),
        "delegations": [d.model_dump() for d in deps.delegations],
        "usage": deps.usage_total,
        "limits": {
            "requests_boss": MAX_REQUESTS_BOSS,
            "requests_specialist": MAX_REQUESTS_SPECIALIST,
            "delegation_depth": MAX_DELEGATION_DEPTH,
            "delegations_per_ticket": MAX_DELEGATIONS_PER_TICKET,
        },
    }


@app.get("/events", tags=["board"])
async def get_events(
    after_id: int = -1, limit: int = 60, ticket_id: int | None = None, run_id: str | None = None
) -> dict:
    """Recent agent activity: what each agent said and which tools it used.

    Each event carries a monotonic ``id`` (its position in the trail), so the
    dashboard can poll with ``?after_id=`` and receive only what is new instead
    of re-reading the whole file.

    Args:
        after_id: Return only events with a higher id. Default returns the tail.
        limit: Maximum events to return.
        ticket_id: Filter to one ticket.
        run_id: Filter to one run.
    """
    events = audit.read_all()
    shaped: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        if index <= after_id:
            continue
        if ticket_id is not None and event.get("ticket_id") != ticket_id:
            continue
        if run_id is not None and event.get("run_id") != run_id:
            continue
        shaped.append(
            {
                "id": index,
                "run_id": event.get("run_id"),
                "ts": event.get("ts"),
                "shop_date": event.get("shop_date"),
                "ticket_id": event.get("ticket_id"),
                "agent": event.get("agent"),
                "parent_agent": event.get("parent_agent"),
                "depth": event.get("depth", 0),
                "kind": event.get("kind"),
                "said": event.get("text", ""),
                "tools_used": [
                    {"tool": call.get("tool"), "args": call.get("args", {})}
                    for call in event.get("tool_calls", [])
                ],
                "tool_results": event.get("tool_returns", []),
                "usage": event.get("usage", {}),
                "note": event.get("note", ""),
            }
        )

    tail = shaped[-limit:] if after_id < 0 else shaped[:limit]
    return {
        "count": len(tail),
        "total_events": len(events),
        "last_id": tail[-1]["id"] if tail else after_id,
        "events": tail,
    }


@app.get("/approvals", tags=["money"])
async def get_approvals(status: str = "pending") -> dict:
    """Requests the agents have prepared for a human.

    The dashboard needs this to render the approve buttons — a request has to be
    visible before anyone can click it. Pass ``all`` for the full history,
    including what has already been executed.
    """
    return await call_tool("list_approvals", {"status": status})


@app.post("/approvals/{approval_id}/approve", tags=["money"])
async def approve(approval_id: int, body: ApproveRequest) -> dict:
    """A human approves (or rejects) a prepared request. **This is what moves cash.**

    Two steps, in order:

    1. Record the decision against the approval, with the person's name.
    2. If approved and it is a payment, settle it — ``pay_invoice`` for an
       invoice, ``pay_rent`` for a lease. Those tools re-check everything:
       the approval must match, and the balance must cover it. A payment that
       would overdraw the account is refused and nothing moves.

    A ``purchase_order`` or ``price_override`` is approved but not "paid" — there
    is no money movement to make, so the request is simply marked approved and
    the shop acts on it elsewhere.

    Returns both the decision and the payment outcome, including a refusal, so
    the dashboard can show what actually happened rather than assuming success.
    """
    approvals = (await call_tool("list_approvals", {"status": "all"}))["approvals"]
    approval = next((a for a in approvals if a["id"] == approval_id), None)
    if approval is None:
        raise HTTPException(status_code=404, detail=f"No approval {approval_id}.")
    if approval["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Approval {approval_id} is already {approval['status']}; it cannot be decided again.",
        )

    decision = await call_tool(
        "record_human_decision",
        {
            "approval_id": approval_id,
            "decision": body.decision,
            "decided_by": body.decided_by,
            "note": body.note,
        },
    )
    if not decision.get("ok"):
        raise HTTPException(status_code=400, detail=decision.get("message", "Decision refused."))

    payment: dict | None = None
    if body.decision == "approved":
        if approval["kind"] == "invoice_payment":
            payment = await call_tool(
                "pay_invoice", {"invoice_id": approval["ref_id"], "approval_id": approval_id}
            )
        elif approval["kind"] == "rent_payment":
            payment = await call_tool(
                "pay_rent", {"lease_id": approval["ref_id"], "approval_id": approval_id}
            )

    cash = await call_tool("get_cash_balance", {"account": "checking"})
    return {
        "approval_id": approval_id,
        "kind": approval["kind"],
        "decision": decision,
        "payment": payment,
        "money_moved": bool(payment and payment.get("ok")),
        "balance_after": cash["balance"],
    }


@app.get("/cash", tags=["money"])
async def get_cash(account: str = "checking") -> dict:
    """The current balance, plus what is already queued against it.

    Cash only leaves in this shop — no revenue is modelled — so the balance is a
    shrinking budget. ``balance_if_all_paid`` shows what would be left if every
    pending and approved request were settled.
    """
    cash = await call_tool("get_cash_balance", {"account": account})
    if not cash.get("found"):
        raise HTTPException(status_code=404, detail=f"No account {account!r}.")
    payments = await call_tool("list_payments")
    return {**cash, "payments_made": payments["count"], "total_paid": payments["total_paid"]}


@app.post("/reset", tags=["admin"])
async def reset() -> dict:
    """Restore the shop database to its original values for a fresh run.

    Wipes every payment, approval, draft and ticket change the team made. The
    pristine ``data/campus_customs.db`` is never written to, and the audit trail
    is **not** cleared — it is append-only, so the history of previous runs
    survives a reset on purpose.
    """
    result = await call_tool("reset_shop_database")
    cash = await call_tool("get_cash_balance")
    return {
        **result,
        "balance": cash["balance"],
        "audit_trail": "preserved (append-only; a reset does not erase run history)",
    }

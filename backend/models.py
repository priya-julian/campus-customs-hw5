"""Data types shared across the Campus Customs agent team.

These are the shapes that cross boundaries: what an agent returns, what gets
written to the audit trail, and what the dashboard will read.  Shop *facts*
(stock, invoices, leases, cash) are deliberately **not** modelled here — those
live in the database and arrive only as MCP tool results, so there is no second
copy of shop truth to drift out of date.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]

ROLE_LABELS: dict[str, str] = {
    "boss": "Boss",
    "inventory": "Inventory",
    "accounting": "Accounting",
    "facilities": "Facilities",
    "customer_service": "Customer Service",
}

#: Every agent may delegate to every other agent — full connectivity.
#: A role never appears in its own peer list.
def peers_of(role: str) -> list[str]:
    return [r for r in ROLE_LABELS if r != role]


class AgentReport(BaseModel):
    """What a specialist hands back to whoever asked it.

    ``findings`` must be traceable to tool results; ``open_questions`` is where
    an agent says what it could not establish, instead of filling the gap in.
    """

    summary: str = Field(description="Two or three sentences a human can act on.")
    findings: list[str] = Field(
        default_factory=list,
        description="Concrete facts from tool results, with the numbers included.",
    )
    actions_taken: list[str] = Field(
        default_factory=list, description="Tool calls that changed the database."
    )
    approvals_requested: list[int] = Field(
        default_factory=list, description="approval_id values now waiting on a human."
    )
    open_questions: list[str] = Field(
        default_factory=list, description="What could not be established from the tools."
    )


class TicketVerdict(BaseModel):
    """The Boss's final call on one ticket."""

    ticket_id: int
    disposition: Literal["resolved", "waiting_approval", "blocked", "needs_human"] = Field(
        description="Where the ticket stands once the team has finished with it."
    )
    reasoning: str = Field(description="Why this disposition, in plain language.")
    consulted: list[str] = Field(
        default_factory=list, description="Roles the Boss delegated to for this ticket."
    )
    actions_taken: list[str] = Field(default_factory=list)
    approvals_requested: list[int] = Field(default_factory=list)
    customer_message_drafted: bool = False
    next_step_for_human: str = Field(
        default="", description="The one thing a person needs to do next, if anything."
    )


class Delegation(BaseModel):
    """One agent asking another for help — the edge the dashboard draws."""

    from_role: str
    to_role: str
    question: str
    depth: int
    answer_summary: str = ""


class AuditEvent(BaseModel):
    """One appended line of the audit trail.

    One event per agent-loop step, plus run-level bookends. Enough to
    reconstruct afterwards who asked what, which tools ran with which
    arguments, what came back, and what it cost.
    """

    run_id: str
    seq: int
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    shop_date: str | None = None
    ticket_id: int | None = None
    agent: str
    parent_agent: str | None = None
    depth: int = 0
    step: int = 0
    kind: str = Field(description="run_started | user_prompt | model_response | model_request | delegation | end | run_finished | error")
    model: str | None = None
    text: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_returns: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    note: str = ""


class RunResult(BaseModel):
    """What one pass over the board produced."""

    run_id: str
    shop_date: str
    tickets_processed: list[int] = Field(default_factory=list)
    verdicts: list[TicketVerdict] = Field(default_factory=list)
    delegations: list[Delegation] = Field(default_factory=list)
    usage_total: dict[str, Any] = Field(default_factory=dict)
    stopped_reason: str = "completed"

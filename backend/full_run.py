"""Drive a complete, reproducible pass over the board, human decisions included.

For each ticket in turn:

1. Run the agent team on it.
2. Act as the human on anything they put up for approval, applying the policy
   below, and let the backend settle any payment that follows.
3. Run the team again so the Boss can see the new state of the shop and close
   the ticket, repeating until it reaches a terminal status.

Everything goes through the FastAPI backend on :8000, which goes through the MCP
server, so this driver is bound by exactly the same guardrails as the dashboard.
Cash is snapshotted before and after every ticket so the ledger can be itemised
afterwards without reconstructing it from memory.

    python backend/full_run.py            # assumes the shop was just reset
    python backend/full_run.py --reset    # reset first
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE = "http://localhost:8000"
APPROVER = "Julian"
TERMINAL = {"resolved", "blocked"}
MAX_PASSES = 4  # room to request, get approved, then execute
API_RETRIES = 3
# Failures worth retrying: the provider hiccuped, not the shop logic.
TRANSIENT = ("Connection error", "ModelAPIError", "timeout", "Timeout",
             "502", "503", "504", "Overloaded")
OUT = Path(__file__).resolve().parent.parent / "output" / "full_run_log.json"


def decide(approval: dict, balance: float) -> tuple[str, str]:
    """The human's policy, written down so the run is reproducible.

    Payments that clear a real obligation get approved when the cash is there.
    Anything that would overdraw the account is rejected with the reason, rather
    than sent to a pay tool that would refuse it anyway.
    """
    amount = approval.get("amount") or 0.0
    kind = approval["kind"]
    SPENDS = {"invoice_payment", "rent_payment", "purchase_order"}

    # The affordability test applies only to money leaving the shop. A price
    # override is what the shop charges, not what it pays, so comparing it to
    # the balance would reject a perfectly good discount.
    if kind in SPENDS and amount > balance:
        return "rejected", (
            f"Rejected: checking holds {balance:,.2f} and this asks for {amount:,.2f}. "
            "Cash only leaves this shop, so it cannot be funded."
        )
    if kind == "invoice_payment":
        return "approved", "Overdue, and it is the only thing freezing the vendor. Clear it."
    if kind == "rent_payment":
        return "approved", "Rent is contractual and due. Pay it."
    if kind == "purchase_order":
        return "approved", f"Affordable at {amount:,.2f} against a {balance:,.2f} balance."
    if kind == "price_override":
        return "approved", "Margin holds at the proposed price."
    return "rejected", "Unrecognised request kind."


async def main(reset: bool) -> None:
    log: dict = {"started": datetime.now(timezone.utc).isoformat(), "tickets": [], "decisions": []}

    async with httpx.AsyncClient(timeout=900) as http:
        if reset:
            await http.post(f"{BASE}/reset")

        opening = (await http.get(f"{BASE}/cash")).json()["balance"]
        log["opening_balance"] = opening
        print(f"opening balance: {opening:,.2f}\n")

        for ticket_id in (101, 102, 103):
            before = (await http.get(f"{BASE}/cash")).json()["balance"]
            entry: dict = {
                "ticket_id": ticket_id,
                "balance_before": before,
                "passes": [],
                "decisions": [],
                # Set before any pass runs, so a failed first pass still leaves
                # a readable record rather than a KeyError.
                "status_after_pass": "unknown",
            }
            print(f"--- ticket {ticket_id} (balance {before:,.2f}) ---")

            for attempt in range(1, MAX_PASSES + 1):
                # A pass can fail transiently — the model provider drops a
                # connection now and then. Losing a 30-minute board run to one
                # network blip is not acceptable, so retry those; a real fault
                # (a usage limit, a bad ticket) is reported and ends the ticket.
                run, detail = None, ""
                for retry in range(1, API_RETRIES + 1):
                    response = await http.post(f"{BASE}/tickets/{ticket_id}/run", json={})
                    candidate = response.json()
                    if "verdict" in candidate:
                        run = candidate
                        break
                    detail = str(candidate.get("detail", response.text))[:300]
                    if not any(sign in detail for sign in TRANSIENT):
                        break
                    print(f"    transient failure ({detail[:60]}…), retry {retry}/{API_RETRIES}")
                    await asyncio.sleep(5 * retry)

                if run is None:
                    entry["passes"].append({"pass": attempt, "failed": detail})
                    print(f"  pass {attempt}: FAILED — {detail}")
                    break
                verdict = run["verdict"]
                entry["passes"].append(
                    {
                        "pass": attempt,
                        "run_id": run["run_id"],
                        "disposition": verdict["disposition"],
                        "consulted": verdict["consulted"],
                        "delegations": run["delegations"],
                        "approvals_requested": verdict["approvals_requested"],
                        "usage": run["usage"],
                        "verdict": verdict,
                    }
                )
                print(f"  pass {attempt}: {verdict['disposition']} (consulted {verdict['consulted']})")

                # Act as the human on anything now pending.
                pending = (await http.get(f"{BASE}/approvals?status=pending")).json()["approvals"]
                acted = False
                for approval in pending:
                    balance = (await http.get(f"{BASE}/cash")).json()["balance"]
                    decision, why = decide(approval, balance)
                    result = (
                        await http.post(
                            f"{BASE}/approvals/{approval['id']}/approve",
                            json={"decided_by": APPROVER, "decision": decision, "note": why},
                        )
                    ).json()
                    record = {
                        "approval_id": approval["id"],
                        "ticket_id": approval["ticket_id"],
                        "kind": approval["kind"],
                        "subject": approval["subject"],
                        "amount": approval["amount"],
                        "requested_by": approval["requested_by"],
                        "rationale": approval["rationale"],
                        "decision": decision,
                        "decided_by": APPROVER,
                        "reason": why,
                        "money_moved": result.get("money_moved", False),
                        "balance_after": result.get("balance_after"),
                        "payment": result.get("payment"),
                    }
                    entry["decisions"].append(record)
                    log["decisions"].append(record)
                    acted = True
                    moved = f"paid, balance {result['balance_after']:,.2f}" if record["money_moved"] else "no money moved"
                    print(f"    human {decision} #{approval['id']} {approval['kind']} "
                          f"{approval['amount']} -> {moved}")

                status = next(
                    t for t in (await http.get(f"{BASE}/tickets")).json()["tickets"]
                    if t["id"] == ticket_id
                )["status"]
                entry["status_after_pass"] = status

                if status in TERMINAL:
                    print(f"  ticket {ticket_id} is {status}")
                    break
                if not acted and attempt > 1:
                    # Nothing changed and nothing to decide: another pass would
                    # just spend tokens repeating itself.
                    print(f"  ticket {ticket_id} settled at {status}; no further change possible")
                    break

            after = (await http.get(f"{BASE}/cash")).json()["balance"]
            entry["balance_after"] = after
            entry["cash_change"] = round(after - before, 2)
            entry["final_status"] = entry["status_after_pass"]
            log["tickets"].append(entry)
            print(f"  balance {before:,.2f} -> {after:,.2f} (change {after - before:+,.2f})\n")

        closing = (await http.get(f"{BASE}/cash")).json()
        log["closing_balance"] = closing["balance"]
        log["payments_made"] = closing["payments_made"]
        log["total_paid"] = closing["total_paid"]
        log["finished"] = datetime.now(timezone.utc).isoformat()

    OUT.write_text(json.dumps(log, indent=2))
    print(f"opening {log['opening_balance']:,.2f} -> closing {log['closing_balance']:,.2f} "
          f"({log['payments_made']} payments, {log['total_paid']:,.2f} out)")
    print(f"log written to {OUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.reset))

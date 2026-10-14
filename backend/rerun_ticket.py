"""Re-run one ticket and merge the result into output/full_run_log.json.

Used when a ticket stalls on a fixable fault: the shop's state carries forward
unchanged, so the board run stays one continuous story rather than becoming a
second run with a different opening balance.

    python backend/rerun_ticket.py 103
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

from full_run import APPROVER, BASE, MAX_PASSES, TERMINAL, decide

LOG = Path(__file__).resolve().parent.parent / "output" / "full_run_log.json"


async def main(ticket_id: int) -> None:
    log = json.loads(LOG.read_text())
    entry = next(t for t in log["tickets"] if t["ticket_id"] == ticket_id)

    async with httpx.AsyncClient(timeout=900) as http:
        before = (await http.get(f"{BASE}/cash")).json()["balance"]
        entry["balance_before"] = before
        entry["passes"] = []
        entry["decisions"] = []
        entry["rerun_note"] = (
            "Re-run after a validation fix; the shop state carried forward unchanged "
            f"from the first attempt (balance {before:,.2f})."
        )
        print(f"re-running ticket {ticket_id} from balance {before:,.2f}")

        for attempt in range(1, MAX_PASSES + 1):
            response = await http.post(f"{BASE}/tickets/{ticket_id}/run", json={})
            run = response.json()
            if "verdict" not in run:
                detail = str(run.get("detail", response.text))[:300]
                entry["passes"].append({"pass": attempt, "failed": detail})
                print(f"  pass {attempt}: FAILED — {detail}")
                break
            verdict = run["verdict"]
            entry["passes"].append({
                "pass": attempt, "run_id": run["run_id"],
                "disposition": verdict["disposition"], "consulted": verdict["consulted"],
                "delegations": run["delegations"],
                "approvals_requested": verdict["approvals_requested"],
                "usage": run["usage"], "verdict": verdict,
            })
            print(f"  pass {attempt}: {verdict['disposition']} (consulted {verdict['consulted']})")

            pending = (await http.get(f"{BASE}/approvals?status=pending")).json()["approvals"]
            acted = False
            for approval in pending:
                balance = (await http.get(f"{BASE}/cash")).json()["balance"]
                decision, why = decide(approval, balance)
                result = (await http.post(
                    f"{BASE}/approvals/{approval['id']}/approve",
                    json={"decided_by": APPROVER, "decision": decision, "note": why},
                )).json()
                record = {
                    "approval_id": approval["id"], "ticket_id": approval["ticket_id"],
                    "kind": approval["kind"], "subject": approval["subject"],
                    "amount": approval["amount"], "requested_by": approval["requested_by"],
                    "rationale": approval["rationale"], "decision": decision,
                    "decided_by": APPROVER, "reason": why,
                    "money_moved": result.get("money_moved", False),
                    "balance_after": result.get("balance_after"), "payment": result.get("payment"),
                }
                entry["decisions"].append(record)
                log.setdefault("decisions", []).append(record)
                acted = True
                moved = (f"paid, balance {result['balance_after']:,.2f}"
                         if record["money_moved"] else "no money moved")
                print(f"    human {decision} #{approval['id']} {approval['kind']} "
                      f"{approval['amount']} -> {moved}")

            status = next(t for t in (await http.get(f"{BASE}/tickets")).json()["tickets"]
                          if t["id"] == ticket_id)["status"]
            entry["status_after_pass"] = status
            if status in TERMINAL:
                print(f"  ticket {ticket_id} is {status}")
                break
            if not acted and attempt > 1:
                print(f"  ticket {ticket_id} settled at {status}")
                break

        after = (await http.get(f"{BASE}/cash")).json()["balance"]
        entry["balance_after"] = after
        entry["cash_change"] = round(after - before, 2)
        entry["final_status"] = entry["status_after_pass"]

        closing = (await http.get(f"{BASE}/cash")).json()
        log["closing_balance"] = closing["balance"]
        log["payments_made"] = closing["payments_made"]
        log["total_paid"] = closing["total_paid"]
        log["finished"] = datetime.now(timezone.utc).isoformat()

    LOG.write_text(json.dumps(log, indent=2))
    print(f"  balance {before:,.2f} -> {after:,.2f}")
    print(f"closing {log['closing_balance']:,.2f} ({log['payments_made']} payments)")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))

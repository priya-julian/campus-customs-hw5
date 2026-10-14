"""Build the Problem 9 deliverables from the recorded full run.

Reads ``output/full_run_log.json`` (written by full_run.py) and the audit trail,
then produces:

* ``output/resolved_tickets.json`` — per ticket: id, final status, outcome, what
  each agent contributed, and the human approvals
* the Actual sections and the Cash tab of ``output/desk_tickets.html``

Every figure is read back from the database or the run log; nothing here is
typed in by hand, so the cash itemisation cannot drift from what actually
happened.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "output" / "full_run_log.json"
TRAIL = ROOT / "output" / "audit_trail.json"
DB = ROOT / "data" / "campus_customs_new.db"

ROLE_LABEL = {
    "boss": "Boss", "inventory": "Inventory", "accounting": "Accounting",
    "facilities": "Facilities", "customer_service": "Customer Service",
}


def db_rows(sql: str, params: tuple = ()) -> list[dict]:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def load() -> tuple[dict, list[dict]]:
    return json.loads(LOG.read_text()), json.loads(TRAIL.read_text())


def run_ids_for(entry: dict) -> list[str]:
    return [p["run_id"] for p in entry["passes"] if "run_id" in p]


def events_for(trail: list[dict], run_ids: list[str], ticket_id: int) -> list[dict]:
    wanted = set(run_ids)
    return [e for e in trail if e.get("run_id") in wanted and e.get("ticket_id") == ticket_id]


def agent_contributions(events: list[dict]) -> dict[str, dict]:
    """Per agent: tools actually called, and their closing summary."""
    out: dict[str, dict] = {}
    for e in events:
        role = e["agent"]
        slot = out.setdefault(role, {"agent": ROLE_LABEL.get(role, role), "steps": 0,
                                     "tools_used": [], "summary": ""})
        slot["steps"] += 1
        for call in e.get("tool_calls", []):
            tool = call.get("tool", "")
            if tool and tool != "final_result":
                slot["tools_used"].append(tool.replace("campus-customs_", ""))
        if e["kind"] == "end":
            try:
                parsed = json.loads(e.get("text", ""))
                slot["summary"] = parsed.get("summary") or parsed.get("reasoning", "")
            except (json.JSONDecodeError, TypeError):
                pass
    for slot in out.values():
        seen: list[str] = []
        for tool in slot["tools_used"]:
            if tool not in seen:
                seen.append(tool)
        slot["tools_used"] = seen
    return out


def delegations_for(entry: dict) -> list[dict]:
    out = []
    for p in entry["passes"]:
        for d in p.get("delegations", []):
            out.append({
                "pass": p["pass"],
                "from": ROLE_LABEL.get(d["from_role"], d["from_role"]),
                "to": ROLE_LABEL.get(d["to_role"], d["to_role"]),
                "depth": d["depth"],
                "direct_between_specialists": d["depth"] >= 2,
                "question": d["question"][:300],
            })
    return out


def build_resolved_tickets(log: dict, trail: list[dict]) -> dict:
    tickets = {t["id"]: t for t in db_rows("SELECT * FROM tickets")}
    drafts = db_rows("SELECT * FROM drafts")
    payload = {
        "shop_date": db_rows("SELECT date_today FROM desk")[0]["date_today"],
        "opening_balance": log["opening_balance"],
        "closing_balance": log["closing_balance"],
        "payments_made": log["payments_made"],
        "total_paid": log["total_paid"],
        "tickets": [],
    }

    for entry in log["tickets"]:
        tid = entry["ticket_id"]
        events = events_for(trail, run_ids_for(entry), tid)
        contributions = agent_contributions(events)
        final_verdict = next(
            (p["verdict"] for p in reversed(entry["passes"]) if "verdict" in p), None
        )
        payload["tickets"].append({
            "id": tid,
            "subject": tickets[tid]["subject"],
            "requester": tickets[tid]["requester"],
            "final_status": tickets[tid]["status"],
            "outcome": (final_verdict or {}).get("reasoning", "")[:600],
            "next_step_for_human": (final_verdict or {}).get("next_step_for_human", ""),
            "passes_run": len(entry["passes"]),
            "agents_involved": sorted(contributions),
            "agent_contributions": list(contributions.values()),
            "delegations": delegations_for(entry),
            "human_approvals": [
                {
                    "approval_id": d["approval_id"],
                    "kind": d["kind"],
                    "amount": d["amount"],
                    "requested_by": ROLE_LABEL.get(d["requested_by"], d["requested_by"]),
                    "decision": d["decision"],
                    "decided_by": d["decided_by"],
                    "reason": d["reason"],
                    "money_moved": d["money_moved"],
                    "balance_after": d["balance_after"],
                }
                for d in entry["decisions"]
            ],
            "cash_change": entry["cash_change"],
            "balance_before": entry["balance_before"],
            "balance_after": entry["balance_after"],
            "customer_drafts": [
                {"draft_id": d["id"], "recipient": d["recipient"], "subject": d["subject"],
                 "status": d["status"]}
                for d in drafts if d["ticket_id"] == tid
            ],
        })
    return payload


if __name__ == "__main__":
    log, trail = load()
    resolved = build_resolved_tickets(log, trail)
    out = ROOT / "output" / "resolved_tickets.json"
    out.write_text(json.dumps(resolved, indent=2))
    print(f"wrote {out.relative_to(ROOT)}")
    for t in resolved["tickets"]:
        print(f"  #{t['id']} {t['final_status']:<18} agents={len(t['agents_involved'])} "
              f"approvals={len(t['human_approvals'])} cash {t['cash_change']:+,.2f}")
    print(f"opening {resolved['opening_balance']:,.2f} -> closing {resolved['closing_balance']:,.2f}")

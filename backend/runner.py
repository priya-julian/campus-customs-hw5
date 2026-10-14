"""Drive the Campus Customs team over the ticket board.

``work_ticket`` runs one ticket: the Boss reads it, delegates as it sees fit, and
returns a verdict.  ``work_board`` runs every open ticket in order.  Both write
the whole agent loop to the append-only audit trail as they go.

Run a full pass from the command line::

    python backend/runner.py --reset        # reset the shop first, then work the board
    python backend/runner.py --ticket 101   # one ticket, no reset
"""

from __future__ import annotations

import argparse
import asyncio
import json

import audit
from config import MODEL_NAME
from models import AuditEvent, RunResult, TicketVerdict
from team import TeamDeps, get_agent, new_run_id, run_traced

BOSS_TASK = """Work ticket {ticket_id} for Campus Customs.

Read the ticket with campus-customs_get_ticket first, decide which teammates
should handle which part of it, delegate to them with ask_teammate, and then make
the final call. Record where the ticket landed with campus-customs_update_ticket
before you finish."""


async def work_ticket(ticket_id: int, *, run_id: str | None = None) -> tuple[TicketVerdict, TeamDeps]:
    """Run the team on one ticket and return the Boss's verdict."""
    from mcp_tools import call_tool  # local import keeps the module import cheap

    run_id = run_id or new_run_id()
    shop_date = (await call_tool("get_shop_date"))["shop_today"]

    deps = TeamDeps(run_id=run_id, ticket_id=ticket_id, shop_date=shop_date, current_role="boss")
    audit.append(
        AuditEvent(
            run_id=run_id, seq=deps.next_seq(), shop_date=shop_date, ticket_id=ticket_id,
            agent="boss", kind="run_started", model=MODEL_NAME,
            note=f"Working ticket {ticket_id} on shop date {shop_date}.",
        )
    )

    boss = get_agent("boss")
    try:
        async with boss:
            verdict = await run_traced(
                boss, BOSS_TASK.format(ticket_id=ticket_id), deps=deps, role="boss"
            )
    except Exception as exc:  # noqa: BLE001 - the trail must record the failure
        audit.append(
            AuditEvent(
                run_id=run_id, seq=deps.next_seq(), shop_date=shop_date, ticket_id=ticket_id,
                agent="boss", kind="error", text=f"{type(exc).__name__}: {exc}",
            )
        )
        raise

    audit.append(
        AuditEvent(
            run_id=run_id, seq=deps.next_seq(), shop_date=shop_date, ticket_id=ticket_id,
            agent="boss", kind="run_finished", model=MODEL_NAME,
            text=verdict.model_dump_json(), usage=deps.usage_total,
            note=f"{len(deps.delegations)} delegation(s): "
                 + ", ".join(f"{d.from_role}->{d.to_role}" for d in deps.delegations),
        )
    )
    return verdict, deps


async def work_board(*, reset: bool = False) -> RunResult:
    """Run the team over every open ticket on the board."""
    from mcp_tools import call_tool

    run_id = new_run_id()
    if reset:
        await call_tool("reset_shop_database")

    shop_date = (await call_tool("get_shop_date"))["shop_today"]
    board = await call_tool("list_tickets", {"status": "open"})

    result = RunResult(run_id=run_id, shop_date=shop_date)
    for ticket in board["tickets"]:
        verdict, deps = await work_ticket(ticket["id"], run_id=run_id)
        result.tickets_processed.append(ticket["id"])
        result.verdicts.append(verdict)
        result.delegations.extend(deps.delegations)
        for key, value in deps.usage_total.items():
            result.usage_total[key] = result.usage_total.get(key, 0) + value
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Campus Customs agent team.")
    parser.add_argument("--ticket", type=int, help="Work a single ticket id.")
    parser.add_argument("--reset", action="store_true", help="Reset the shop database first.")
    args = parser.parse_args()

    async def go():
        if args.ticket:
            from mcp_tools import call_tool

            if args.reset:
                await call_tool("reset_shop_database")
            verdict, _ = await work_ticket(args.ticket)
            print(verdict.model_dump_json(indent=2))
        else:
            result = await work_board(reset=args.reset)
            print(result.model_dump_json(indent=2))

    asyncio.run(go())


if __name__ == "__main__":
    main()

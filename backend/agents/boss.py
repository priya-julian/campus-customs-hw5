"""Boss agent — owns the board and makes the final call.

Role prompt: `backend/prompts/boss.md`
Shop access: the campus-customs MCP server only, over
`data/campus_customs_new.db`.
Model: gpt-6-luna via Portkey, fixed in `backend/config.py`.

Reads each ticket with its linked records, routes the work to whichever
teammates the ticket actually touches, weighs what they report, and decides the
disposition. The only role that closes a ticket, and the only one that returns a
`TicketVerdict` rather than an `AgentReport`. It cannot approve payments: that
is the human's tool.
"""

from __future__ import annotations

from team import build_role_agent

ROLE = "boss"


def build():
    """Build the Boss agent."""
    return build_role_agent(ROLE)

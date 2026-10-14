"""Customer Service agent — writes what the customer reads.

Role prompt: `backend/prompts/customer_service.md`
Shop access: the campus-customs MCP server only, over
`data/campus_customs_new.db`.
Model: gpt-6-luna via Portkey, fixed in `backend/config.py`.

Gathers facts from whichever teammate owns them, then drafts a reply in which
every claim is backed by a tool result. Conditional things are written as
conditional. Drafts are saved to the board as `draft_not_sent` — there is no
send tool on this server.
"""

from __future__ import annotations

from team import build_role_agent

ROLE = "customer_service"


def build():
    """Build the Customer Service agent."""
    return build_role_agent(ROLE)

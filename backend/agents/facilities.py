"""Facilities agent — owns the shop space.

Role prompt: `backend/prompts/facilities.md`
Shop access: the campus-customs MCP server only, over
`data/campus_customs_new.db`.
Model: gpt-6-luna via Portkey, fixed in `backend/config.py`.

Verifies a rent notice against the shop's own lease record before anyone acts
on it, reports whether rent is upcoming, due, or late by the shop's calendar,
and hands the verified figures to Accounting for the approval request. Does not
pay and does not reply to the landlord.
"""

from __future__ import annotations

from team import build_role_agent

ROLE = "facilities"


def build():
    """Build the Facilities agent."""
    return build_role_agent(ROLE)

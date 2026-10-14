"""Accounting agent — owns the cash, the invoices, and the margins.

Role prompt: `backend/prompts/accounting.md`
Shop access: the campus-customs MCP server only, over
`data/campus_customs_new.db`.
Model: gpt-6-luna via Portkey, fixed in `backend/config.py`.

Reads the balance together with everything already queued against it, judges
overdue against the shop's own date, and writes the approval requests a human
decides from. Prepares payments and purchase orders; releases nothing. Scores
discounts against cost and recommends, but never approves.
"""

from __future__ import annotations

from team import build_role_agent

ROLE = "accounting"


def build():
    """Build the Accounting agent."""
    return build_role_agent(ROLE)

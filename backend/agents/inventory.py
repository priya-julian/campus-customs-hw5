"""Inventory agent — owns the shelf and the restock path.

Role prompt: `backend/prompts/inventory.md`
Shop access: the campus-customs MCP server only, over
`data/campus_customs_new.db`.
Model: gpt-6-luna via Portkey, fixed in `backend/config.py`.

Answers supply questions at the SKU *and size* level, works out shortfalls from
tool results rather than arithmetic, and finds the vendor who can resupply —
including whether that vendor is blocked by an unpaid invoice, which is what
decides whether a delivery date is real or conditional.
"""

from __future__ import annotations

from team import build_role_agent

ROLE = "inventory"


def build():
    """Build the Inventory agent."""
    return build_role_agent(ROLE)

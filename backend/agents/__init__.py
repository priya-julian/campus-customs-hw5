"""The five Campus Customs roles, one module each.

Each module names its role, points at its prompt, and builds its agent. The
registry here is what ``team.get_agent`` resolves against, so adding a sixth
role means adding a file here rather than editing the wiring.

Imports are deferred to call time because the role modules import ``team`` and
``team`` resolves agents through this package.
"""

from __future__ import annotations

from importlib import import_module

ROLES = ["boss", "inventory", "accounting", "facilities", "customer_service"]


def build(role: str):
    """Build the agent for ``role`` from its own module."""
    if role not in ROLES:
        raise ValueError(f"Unknown role {role!r}. Known roles: {', '.join(ROLES)}.")
    return import_module(f"agents.{role}").build()

"""The Campus Customs agent team: five roles, fully connected.

Every agent is built the same way — same model (gpt-6-luna via Portkey), same
MCP toolset over ``data/campus_customs_new.db`` — and differs only in its prompt
and its output type.  On top of the shop tools, every agent gets one extra tool,
``ask_teammate``, which can reach **any** of the other four.  That is the full
connectivity: there is no fixed hierarchy in the wiring, only the Boss's prompt
telling it that routing is its job.

Delegation is bounded so a confused team cannot spend the budget:

* ``MAX_DELEGATION_DEPTH`` — how deep a chain of hand-offs may go
* ``MAX_DELEGATIONS_PER_TICKET`` — how many hand-offs one ticket may use in total
* ``UsageLimits`` — model requests and tool calls inside any single agent loop

Every loop node of every agent is written to the append-only audit trail.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import RetryPromptPart, TextPart, ThinkingPart, ToolCallPart, ToolReturnPart
from pydantic_ai.usage import UsageLimits

import audit
from config import (
    MAX_DELEGATION_DEPTH,
    MAX_DELEGATIONS_PER_TICKET,
    MAX_REQUESTS_BOSS,
    MAX_REQUESTS_SPECIALIST,
    MAX_TOOL_CALLS_PER_AGENT,
    MODEL_NAME,
    build_model,
    load_prompt,
    shop_toolset,
)
from models import AgentReport, AuditEvent, Delegation, ROLE_LABELS, TicketVerdict, peers_of

SPECIALISTS = ["inventory", "accounting", "facilities", "customer_service"]
ALL_ROLES = ["boss", *SPECIALISTS]

def limits_for(role: str) -> UsageLimits:
    """Request budget for one agent's loop, by role."""
    return UsageLimits(
        request_limit=MAX_REQUESTS_BOSS if role == "boss" else MAX_REQUESTS_SPECIALIST,
        tool_calls_limit=MAX_TOOL_CALLS_PER_AGENT,
    )


# ------------------------------------------------------------------- state


@dataclass
class TeamDeps:
    """Carried through every agent in one ticket's run.

    One instance per ticket, shared by every agent working it, so the hand-off
    budget is genuinely shared rather than reset per agent.
    """

    run_id: str
    ticket_id: int | None = None
    shop_date: str | None = None
    depth: int = 0
    current_role: str = "boss"
    delegations_used: int = 0
    delegations: list[Delegation] = field(default_factory=list)
    usage_total: dict[str, int] = field(default_factory=dict)
    seq: int = 0
    started: float = field(default_factory=time.perf_counter)

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq

    def add_usage(self, usage: dict) -> None:
        for key, value in usage.items():
            if isinstance(value, (int, float)):
                self.usage_total[key] = self.usage_total.get(key, 0) + value

    def child(self, role: str) -> "TeamDeps":
        """Deps for a delegated run: deeper, different role, same shared budget.

        The mutable shared state (``delegations``, ``usage_total``) is passed by
        reference on purpose — a hand-off three levels down still counts against
        the same ticket budget.
        """
        child = TeamDeps(
            run_id=self.run_id,
            ticket_id=self.ticket_id,
            shop_date=self.shop_date,
            depth=self.depth + 1,
            current_role=role,
            delegations=self.delegations,
            usage_total=self.usage_total,
        )
        child._parent = self  # type: ignore[attr-defined]
        return child

    @property
    def parent(self) -> "TeamDeps | None":
        return getattr(self, "_parent", None)


# ------------------------------------------------------------ audit helpers


def _usage_dict(usage: Any) -> dict:
    return {
        "requests": getattr(usage, "requests", 0) or 0,
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "cached_tokens": getattr(usage, "cache_read_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "tool_calls": getattr(usage, "tool_calls", 0) or 0,
    }


def _describe(node: Any) -> tuple[str, dict] | None:
    """Turn one PydanticAI loop node into an auditable record."""
    if Agent.is_user_prompt_node(node):
        return "user_prompt", {"text": audit.clip(node.user_prompt)}

    if Agent.is_model_request_node(node):
        parts = node.request.parts
        returns = [
            {
                "tool": p.tool_name,
                "tool_call_id": p.tool_call_id,
                "result": audit.clip(p.model_response_str()),
            }
            for p in parts
            if isinstance(p, ToolReturnPart)
        ]
        retries = [audit.clip(p.model_response(), 400) for p in parts if isinstance(p, RetryPromptPart)]
        if not returns and not retries:
            return None  # the opening request carries nothing worth a row
        return "model_request", {"tool_returns": returns, "note": "; ".join(retries)}

    if Agent.is_call_tools_node(node):
        resp = node.model_response
        text = "".join(p.content for p in resp.parts if isinstance(p, TextPart))
        thinking = "".join(p.content for p in resp.parts if isinstance(p, ThinkingPart))
        calls = [
            {"tool": p.tool_name, "tool_call_id": p.tool_call_id, "args": p.args_as_dict()}
            for p in resp.parts
            if isinstance(p, ToolCallPart)
        ]
        return "model_response", {
            "model": resp.model_name,
            "text": audit.clip(text),
            "tool_calls": calls,
            "usage": _usage_dict(resp.usage),
            "note": audit.clip(thinking, 300) if thinking else "",
        }

    if Agent.is_end_node(node):
        # Record the structured output as JSON so the dashboard can render an
        # agent's report field by field instead of parsing a Python repr.
        output = node.data.output
        text = output.model_dump_json() if hasattr(output, "model_dump_json") else str(output)
        return "end", {"text": audit.clip(text, 2500)}

    return None


def _record(deps: TeamDeps, *, agent: str, kind: str, step: int = 0, **data: Any) -> None:
    audit.append(
        AuditEvent(
            run_id=deps.run_id,
            seq=deps.next_seq(),
            shop_date=deps.shop_date,
            ticket_id=deps.ticket_id,
            agent=agent,
            parent_agent=deps.parent.current_role if deps.parent else None,
            depth=deps.depth,
            step=step,
            kind=kind,
            **data,
        )
    )


async def run_traced(agent: Agent, prompt: str, *, deps: TeamDeps, role: str):
    """Run one agent, writing an audit event per loop node. Returns its output."""
    step = 0
    async with agent.iter(prompt, deps=deps, usage_limits=limits_for(role)) as run:
        async for node in run:
            described = _describe(node)
            if described is None:
                continue
            step += 1
            kind, data = described
            if kind == "model_response":
                deps.add_usage(data.get("usage", {}))
            _record(deps, agent=role, kind=kind, step=step, **data)
        return run.result.output


# ------------------------------------------------------------- agent build


def _instructions(role: str) -> str:
    """One role's prompt with the shared shop rules spliced in."""
    shared = load_prompt("_shared_rules")
    return load_prompt(role).replace("{shared_rules}", shared)


def build_role_agent(role: str) -> Agent:
    """Build one agent: fixed model, shop tools over MCP, its own prompt.

    Called by the role modules in ``backend/agents/``; use ``get_agent`` to get
    a built, cached agent by role name.
    """
    output_type = TicketVerdict if role == "boss" else AgentReport
    agent = Agent(
        build_model(),
        deps_type=TeamDeps,
        output_type=output_type,
        instructions=_instructions(role),
        toolsets=shop_toolset(),
        name=role,
        retries=2,
    )
    _attach_delegation(agent, role)
    return agent


_AGENTS: dict[str, Agent] = {}


def get_agent(role: str) -> Agent:
    """Agents are built once and reused across tickets.

    Resolved through ``backend/agents/<role>.py`` so each role stays a file of
    its own rather than a string in this module.
    """
    if role not in _AGENTS:
        import agents  # deferred: the role modules import this module

        _AGENTS[role] = agents.build(role)
    return _AGENTS[role]


def _attach_delegation(agent: Agent, role: str) -> None:
    """Give this agent one tool that can reach any of the other four.

    This is what makes the team fully connected: the tool's docstring names
    every peer, and nothing in the wiring privileges the Boss.
    """
    others = peers_of(role)
    roster = ", ".join(f"`{r}` ({ROLE_LABELS[r]})" for r in others)

    description = (
        "Hand a question to another agent on the Campus Customs team and get their "
        f"report back. Available teammates: {roster}. Ask when the question belongs "
        "to someone else's tables. Include the facts you already gathered so they do "
        "not repeat your lookups, and ask one specific question - not 'take a look at "
        "this ticket'."
    )

    @agent.tool(description=description)
    async def ask_teammate(ctx: RunContext[TeamDeps], teammate: str, question: str) -> dict:
        """Delegate to a teammate.

        Args:
            teammate: One of the role names listed in the tool description.
            question: The specific question, with your context included.
        """
        deps = ctx.deps
        if teammate not in others:
            return {
                "ok": False,
                "message": f"{teammate!r} is not on the team. Choose one of: {', '.join(others)}.",
            }
        if deps.depth >= MAX_DELEGATION_DEPTH:
            return {
                "ok": False,
                "limit": "max_depth",
                "message": (
                    f"Hand-off depth limit ({MAX_DELEGATION_DEPTH}) reached. "
                    "Answer with the tools and facts you already have."
                ),
            }
        if deps.delegations_used >= MAX_DELEGATIONS_PER_TICKET or (
            len(deps.delegations) >= MAX_DELEGATIONS_PER_TICKET
        ):
            return {
                "ok": False,
                "limit": "max_delegations",
                "message": (
                    f"This ticket has used its {MAX_DELEGATIONS_PER_TICKET} hand-offs. "
                    "Finish with what the team already established."
                ),
            }

        deps.delegations_used += 1
        record = Delegation(from_role=role, to_role=teammate, question=audit.clip(question, 500),
                            depth=deps.depth + 1)
        deps.delegations.append(record)
        _record(deps, agent=role, kind="delegation",
                text=f"{role} -> {teammate}: {audit.clip(question, 500)}")

        child_deps = deps.child(teammate)
        report = await run_traced(get_agent(teammate), question, deps=child_deps, role=teammate)
        deps.seq = max(deps.seq, child_deps.seq)
        record.answer_summary = audit.clip(report.summary, 300)

        return {
            "ok": True,
            "from": teammate,
            "report": report.model_dump(),
        }


# ------------------------------------------------------------ public entry


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]

"""Model and MCP wiring for the Campus Customs team.

Every agent on this team runs on **gpt-6-luna through Portkey** and reaches shop
data **only** through the MCP server registered in the project's ``.mcp.json``.
Both of those are enforced here rather than left to convention:

* :data:`MODEL_NAME` is fixed and :func:`build_model` refuses any other name, so
  a stray model string cannot reach Portkey.
* :func:`shop_toolset` loads the *same* ``.mcp.json`` the vibe coder uses, so
  there is exactly one tools layer over ``data/campus_customs_new.db``.

The API key is read from the nearest ``.env`` at or above the project folder and
is never logged or written to disk.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.mcp import MCPToolset, StdioTransport
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MCP_CONFIG = PROJECT_ROOT / ".mcp.json"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
AUDIT_PATH = PROJECT_ROOT / "output" / "audit_trail.json"

# Load .env from the project folder and every folder above it; nearest wins.
for folder in [PROJECT_ROOT, *PROJECT_ROOT.parents]:
    env_file = folder / ".env"
    if env_file.is_file():
        load_dotenv(env_file, override=False)

#: The only model this assignment may use. Not configurable on purpose.
MODEL_NAME = "gpt-6-luna"

PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1").rstrip("/")

# ---- token guardrails -------------------------------------------------------
# A ticket is a small question; these caps stop a confused loop from burning the
# course budget. See the safety section of output/harness.md.
# The Boss runs the longest loop — it reads the ticket, delegates several
# times, records the outcome and then writes its verdict — and a second pass
# over an already-worked ticket has more history to read than the first. The
# specialists answer one question each and need far less.
MAX_REQUESTS_BOSS = 16          # model calls inside the Boss's loop
MAX_REQUESTS_SPECIALIST = 10    # model calls inside a specialist's loop
MAX_REQUESTS_PER_AGENT = MAX_REQUESTS_SPECIALIST  # back-compat default
MAX_TOOL_CALLS_PER_AGENT = 20   # tool calls inside one agent's loop
MAX_DELEGATION_DEPTH = 2        # boss -> specialist -> one more hop, then stop
MAX_DELEGATIONS_PER_TICKET = 6  # total peer hand-offs while working one ticket
TOOL_RESULT_CLIP = 1200         # chars of any tool result kept in the audit trail


def require_api_key() -> str:
    """Return PORTKEY_API_KEY, or explain where to put it. Never logged."""
    key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "PORTKEY_API_KEY is missing. Put it in the AI Foundations .env file "
            "(this project reads .env from the project folder and any folder above it)."
        )
    return key


@lru_cache(maxsize=1)
def build_model() -> OpenAIResponsesModel:
    """The one model client every agent shares.

    gpt-6-luna needs the Responses API for function tools — chat/completions
    rejects tools plus reasoning on this model.
    """
    client = AsyncOpenAI(
        api_key=require_api_key(),
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-provider": "openai"},
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def mcp_command() -> tuple[str, list[str]]:
    """The campus-customs server's launch command, as absolute paths.

    ``.mcp.json`` stores paths relative to the project root so the repository
    works on anyone's machine. Those paths are resolved here against the project
    root — not the current working directory — because the backend is started
    from ``backend/`` while the editor loads the same file from the root.
    """
    import json

    entry = json.loads(MCP_CONFIG.read_text())["mcpServers"]["campus-customs"]

    def absolute(value: str) -> str:
        # Deliberately not .resolve(): a virtualenv's bin/python is a symlink to
        # the system interpreter, and following it would launch the server
        # outside the venv, without any of the installed packages.
        path = Path(value)
        return str(path if path.is_absolute() else PROJECT_ROOT / path)

    return absolute(entry["command"]), [absolute(a) for a in entry["args"]]


@lru_cache(maxsize=1)
def shop_toolset():
    """The MCP toolset every agent uses, built from the project's .mcp.json.

    Returned as a list so it can be passed straight to ``Agent(toolsets=...)``.
    Reading the same config file the editor uses is deliberate: there is no
    second, in-process copy of the shop tools that could drift from the server.
    """
    if not MCP_CONFIG.is_file():
        raise RuntimeError(f"No MCP config at {MCP_CONFIG}. Problem 4 creates this file.")
    command, args = mcp_command()
    return [MCPToolset(StdioTransport(command=command, args=args))]


def load_prompt(role: str) -> str:
    """Read one agent's system prompt from backend/prompts/<role>.md."""
    path = PROMPTS_DIR / f"{role}.md"
    if not path.is_file():
        raise FileNotFoundError(f"No prompt for role {role!r} at {path}.")
    return path.read_text(encoding="utf-8")

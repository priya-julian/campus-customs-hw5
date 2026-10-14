"""Append-only audit trail at output/audit_trail.json.

Every agent-loop step across every run lands here. The file is a JSON array and
is **appended to, never wiped** — a new run adds events after the previous run's,
so the history of the shop survives restarts and resets of the database.

One event per loop node means the trail can answer, after the fact: which agent
was running, who asked it to, which tools it called with which arguments, what
came back, what the model said, and how many tokens it spent.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from config import AUDIT_PATH, TOOL_RESULT_CLIP
from models import AuditEvent

_lock = threading.Lock()


def clip(value: Any, limit: int = TOOL_RESULT_CLIP) -> str:
    """Shorten a value for the trail, saying how much was dropped.

    Tool results can be long. The trail keeps enough to audit the decision
    without storing an unbounded copy of the database.
    """
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[:limit] + f"… (+{len(text) - limit} chars)"


def _read(path: Path) -> list[dict]:
    if not path.is_file() or path.stat().st_size == 0:
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # A half-written file must not destroy the history: keep it aside.
        path.rename(path.with_suffix(".corrupt.json"))
        return []
    return data if isinstance(data, list) else [data]


def append(event: AuditEvent) -> None:
    """Append one event to the trail, preserving everything already there."""
    with _lock:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        events = _read(AUDIT_PATH)
        events.append(json.loads(event.model_dump_json()))
        tmp = AUDIT_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(events, indent=2), encoding="utf-8")
        tmp.replace(AUDIT_PATH)


def read_all() -> list[dict]:
    """Every event ever recorded, oldest first."""
    with _lock:
        return _read(AUDIT_PATH)


def read_run(run_id: str) -> list[dict]:
    """Just the events for one run."""
    return [e for e in read_all() if e.get("run_id") == run_id]

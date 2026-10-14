"""Shared SQLite access for the Campus Customs MCP server.

Every tool in this package reads and writes the *working copy* of the shop
database.  The pristine file (``data/campus_customs.db``) is only ever read by
:func:`reset_working_copy`, so a bad run can always be undone.

Two tables are created here rather than shipped in the original file:
``approvals`` and ``drafts``.  They hold the workflow state the agents generate
-- requests waiting on a human, and customer messages that must never be sent.
Keeping them in the same database means there is still exactly one source of
shop truth behind the MCP server.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: The working copy.  All tool reads and writes go here.
DB_PATH = PROJECT_ROOT / "data" / "campus_customs_new.db"

#: The pristine original, kept only so the working copy can be reset.
ORIGINAL_DB_PATH = PROJECT_ROOT / "data" / "campus_customs.db"

WORKFLOW_SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
    id            INTEGER PRIMARY KEY,
    ticket_id     INTEGER,
    kind          TEXT NOT NULL,          -- invoice_payment | rent_payment | purchase_order | price_override
    subject       TEXT NOT NULL,
    amount        REAL,
    account       TEXT,
    ref_table     TEXT,                   -- invoices | leases | pricing | NULL
    ref_id        INTEGER,
    rationale     TEXT NOT NULL,
    requested_by  TEXT NOT NULL,          -- which agent asked
    requested_at  TEXT NOT NULL,          -- shop date
    status        TEXT NOT NULL,          -- pending | approved | rejected | executed
    decided_by    TEXT,                   -- the human
    decided_at    TEXT,
    decision_note TEXT
);

CREATE TABLE IF NOT EXISTS drafts (
    id          INTEGER PRIMARY KEY,
    ticket_id   INTEGER,
    recipient   TEXT NOT NULL,
    subject     TEXT NOT NULL,
    body        TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'draft_not_sent'
);
"""


def connect() -> sqlite3.Connection:
    """Open the working copy with rows that behave like dicts."""
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Working database not found at {DB_PATH}. "
            f"Create it by copying {ORIGINAL_DB_PATH}."
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(WORKFLOW_SCHEMA)
    return conn


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    """Run a SELECT and return every row as a plain dict."""
    with connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    """Run a SELECT and return the first row, or ``None`` if there is no row.

    Returning ``None`` is deliberate: tools report "no such record" rather than
    inventing a plausible one.
    """
    rows = query_all(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple = ()) -> int:
    """Run one INSERT/UPDATE/DELETE and return lastrowid (or rowcount for updates)."""
    with connect() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid if cur.lastrowid else cur.rowcount


def transaction() -> sqlite3.Connection:
    """A connection for multi-statement writes that must land together.

    Paying an invoice touches ``payments``, ``invoices``, ``cash_accounts`` and
    ``approvals``; either all four move or none do.
    """
    return connect()


def today() -> str:
    """The shop's current date, taken from ``desk.date_today``.

    The shop runs on its own clock.  Nothing in this project may use the real
    system date to decide what is overdue.
    """
    row = query_one("SELECT date_today FROM desk LIMIT 1")
    if row is None:
        raise RuntimeError("desk table has no row; cannot determine the shop's date.")
    return row["date_today"]


def days_between(start: str, end: str) -> int:
    """Whole days from ISO date ``start`` to ISO date ``end`` (negative if earlier)."""
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def add_days(start: str, days: int) -> str:
    """ISO date ``days`` after ``start``."""
    from datetime import timedelta

    return (date.fromisoformat(start) + timedelta(days=days)).isoformat()


def add_one_month(iso_date: str) -> str:
    """Same day next month, clamped to the last valid day."""
    d = date.fromisoformat(iso_date)
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            continue
    raise ValueError(f"could not advance {iso_date} by one month")


def reset_working_copy() -> dict:
    """Copy the pristine original over the working copy and rebuild workflow tables.

    This is how a full ticket-resolution run starts from a known state.
    """
    shutil.copyfile(ORIGINAL_DB_PATH, DB_PATH)
    with connect() as conn:
        conn.executescript(WORKFLOW_SCHEMA)
        conn.commit()
    return {
        "reset": True,
        "restored_from": str(ORIGINAL_DB_PATH.relative_to(PROJECT_ROOT)),
        "working_copy": str(DB_PATH.relative_to(PROJECT_ROOT)),
        "shop_today": today(),
    }

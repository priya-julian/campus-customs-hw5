# Campus Customs — Multi-Agent Operations

An agentic back office for a small Yale apparel shop. Tickets land on a board —
customer orders, rent notices, discount requests — and a team of five agents
works them: reading stock, checking cash, drafting replies, and preparing
payments **for a human to approve**.

Three pieces that talk to each other:

| Piece | What it is |
|---|---|
| `mcp_server/` | A FastMCP server with 27 tools over the shop's SQLite database. The only way anything reaches shop data |
| `backend/` | FastAPI + PydanticAI. Five agents, fully connected, all on `gpt-6-luna` through Portkey |
| `frontend/` | A React + Vite + TypeScript dashboard where a human watches the agents and approves payments |

**The rule the whole thing is built around: agents prepare, humans release.**
No agent can move money. `payments.approved_by` always carries a person's name.

---

## Setup

### 1. Clone and create the Python environment

```bash
git clone <this repo>
cd hw5
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### 2. Add your Portkey key

```bash
cp .env.example .env
```

Then edit `.env` and set `PORTKEY_API_KEY` to your own key. The real `.env` is
git-ignored and is never committed.

### 3. Install the dashboard's dependencies

```bash
cd frontend && npm install && cd ..
```

---

## The database — copy the original before a clean run

Two files ship in `data/`:

| File | What it is |
|---|---|
| `campus_customs.db` | **The original.** Never written to by anything in this project |
| `campus_customs_new.db` | **The working copy.** Everything reads and writes here |

Both are committed so the app runs straight after a clone. To start from a clean
shop at any time, copy the original over the working copy:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

That is the manual equivalent of the reset below, and it is worth doing before
any run you intend to grade.

---

## Running it

### Start the MCP server

The server is launched automatically over stdio by the backend and by the
editor, using the relative paths in `.mcp.json`. To run it by hand and confirm
it starts:

```bash
.venv/bin/python mcp_server/server.py
```

It should print `Starting MCP server 'campus-customs' with transport 'stdio'`.
Stop it with Ctrl-C — nothing else needs it running in the background, because
each caller starts its own.

### Start the FastAPI backend

From the `backend/` folder:

```bash
cd backend
uvicorn main:app --reload --port 8000
```

That serves `http://localhost:8000`, with interactive docs at
`http://localhost:8000/docs`.

| Route | What it does |
|---|---|
| `GET /tickets` | All three tickets with status |
| `POST /tickets/{id}/run` | Runs the agent team on one ticket |
| `GET /events` | What each agent said and which tools it used |
| `GET /approvals` | What is waiting on a human |
| `POST /approvals/{id}/approve` | **The only route that moves cash** |
| `GET /cash` | The checking balance |
| `POST /reset` | Restores the working copy from the original |

### Start the React board

In a second terminal:

```bash
cd frontend
npm run dev
```

That opens `http://localhost:5173`. The backend already allows that origin, so
the browser can call it. Pick a ticket, press **Send the team in**, watch the
agents work, and approve payments from the Ledger on the right — type your name
first, because it is recorded as the approver.

---

## Reset the database before a full three-ticket run

Results are only reproducible from a known starting state: **$3,400.00 in
checking, three open tickets, invoice 501 unpaid.** Reset before every full run,
by any of these:

```bash
# from the dashboard
#   press "Reset shop" in the top bar

# from the API
curl -X POST http://localhost:8000/reset

# from the shell
cp data/campus_customs.db data/campus_customs_new.db
```

A reset clears the shop but **not** `output/audit_trail.json` — the trail is
append-only on purpose, so the history of previous runs survives.

Then work the whole board, with the human-approval steps included:

```bash
.venv/bin/python backend/full_run.py --reset
```

That resets, runs each ticket, acts as the approver on anything the team puts
up, and runs it again so the Boss can close it. It takes roughly 25–50 minutes
depending on model latency, and writes `output/full_run_log.json`.

---

## What a clean run produces

| Ticket | Outcome | Cash |
|---|---|---|
| 101 Bulldog tee | `resolved` | −$840.00 (invoice 501, unblocking the vendor) |
| 102 Rent due | `resolved` | −$2,400.00 (September rent) |
| 103 Bulk hoodie discount | `blocked` | $0.00 — the shop is $104 short of the restock |

**$3,400.00 → $160.00.** Ticket 103 is blocked by arithmetic, not by a bad
decision: the board asks for $3,504 against $3,400 of cash, and no ordering of
the three tickets funds all of them.

---

## Where everything is

```
hw5/
├── AI_Prompts.md              every prompt typed into the vibe coder, per problem
├── requirements.txt
├── .env.example               copy to .env and add your key
├── .gitignore
├── .mcp.json                  MCP server registration (relative paths)
├── README.md
├── data/
│   ├── campus_customs.db      the original, never written to
│   └── campus_customs_new.db  the working copy
├── mcp_server/
│   ├── server.py              27 tools over the shop database
│   ├── db.py                  connection, workflow tables, the shop's clock
│   └── README.md
├── frontend/                  React + Vite + TypeScript dashboard
├── backend/
│   ├── main.py                FastAPI routes
│   ├── models.py              shared data types
│   ├── config.py              Portkey + MCP wiring, token limits
│   ├── team.py                agent construction and delegation
│   ├── runner.py              works one ticket or the board
│   ├── audit.py               the append-only trail
│   ├── full_run.py            the full board run, approvals included
│   ├── agents/                one module per role
│   └── prompts/               one prompt per agent
└── output/
    ├── harness.md             tables, tools, agents, routes, dashboard, safety
    ├── mcp_smoke.json         the MCP tool smoke test
    ├── desk_tickets.html      Expected vs Actual per ticket, Cash, Reflection
    ├── design.md              dashboard design reasoning
    ├── resolved_tickets.json  per-ticket outcomes and agent contributions
    ├── resolved_board.html    dashboard screenshots per ticket
    ├── audit_trail.json       every agent-loop step, appended never wiped
    └── github_url.txt
```

---

## The shop's rules

These are enforced in the MCP tools, not in prompts, so an agent cannot talk its
way past them:

- **The shop has its own clock.** `desk.date_today` is 2026-08-31; nothing uses
  the real date to judge what is overdue
- **Human approval for every payment.** The pay tools refuse anything not
  approved by a named person
- **No negative balances.** A payment larger than the balance is refused
  outright, not partially applied
- **Cash only leaves.** No revenue is modelled
- **A vendor owed money will not ship** until the invoice clears
- **Nothing is sent.** Customer messages are saved as `draft_not_sent`. There is
  no send tool and no mail client

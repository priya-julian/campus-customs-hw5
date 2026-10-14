# Campus Customs — Harness

The reference for the whole build: what the shop's data is, what the agents can
do to it, who the agents are, how a human reaches them, and what stops any of it
going wrong.

## What is covered, and where

| Topic | Section |
|---|---|
| **The database tables** — every field, and why it matters to the agents | [Part 1](#part-1--the-tables), with a full data snapshot in [Part 2](#part-2--current-contents) |
| **The three tickets** and how they link to the rest of the shop | [Part 3](#part-3--the-three-open-tickets-and-how-they-link) |
| **Every MCP tool** and the tables it touches | [Problem 5 → Every MCP tool and the table it uses](#every-mcp-tool-and-the-table-it-uses) |
| **The five agents**, their prompts, and how they delegate | [Problem 5 → The team](#the-team) |
| **The API routes** the dashboard calls | [Problem 7 → The routes](#the-routes) |
| **The dashboard** | [Problem 8](#problem-8--the-dashboard), with design reasoning in `output/design.md` |
| **Safety rules and guardrails** | [Problem 5 → Safety](#safety--what-a-real-business-would-want) and [token limits](#limits-that-keep-token-use-in-check) |
| **The full run** — what the team actually did, and the cash | [Problem 9](#problem-9--the-full-run) |

The sections are kept in the order they were built, so the reasoning behind each
decision stays attached to the point where it was made.

---

Working notes on the shop database and the open ticket board.
This file grows as the assignment progresses; Problem 2 adds the database map.

- **Original (never modified):** `data/campus_customs.db`
- **Working copy (all later problems write here):** `data/campus_customs_new.db`
- Both files were byte-identical at copy time (MD5 `46effb90…`), so the working copy can be reset at any point by re-copying the original.

---

## Part 1 — The tables

Nine tables. Fields are listed as `name (type)`; `PK` marks the primary key.

### `desk` — the shop's clock
| Field | Type | Notes |
|---|---|---|
| `date_today` | TEXT | **"Today" for the shop.** Currently `2026-08-31`. |
| `notes` | TEXT | Free text, currently empty. |

**Why it matters:** every "is this overdue?" decision keys off `date_today`, not the real-world clock. Accounting and Facilities must read this table before judging any due date.

---

### `tickets` — the board the agents work
| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER | PK |
| `type` | TEXT | `customer_order`, `rent_notice`, `price_override` so far |
| `requester` | TEXT | Who asked |
| `subject` | TEXT | Short title |
| `sku` | TEXT | → `inventory.sku` / `pricing.sku` (nullable) |
| `size` | TEXT | → `inventory.size` (nullable) |
| `qty` | INTEGER | Units requested (nullable) |
| `lease_id` | INTEGER | FK → `leases.id` (nullable) |
| `invoice_id` | INTEGER | FK → `invoices.id` (nullable) |
| `status` | TEXT | All three currently `open` |
| `notes` | TEXT | The human-readable ask |
| `created_at` | TEXT | ISO timestamp |

**Why it matters:** this is the agents' work queue. The Boss reads `type` and the nullable foreign keys to decide who gets the ticket — a row with a `sku` is Inventory's problem, one with a `lease_id` is Facilities', one with an `invoice_id` is Accounting's.

---

### `inventory` — stock on hand
| Field | Type | Notes |
|---|---|---|
| `sku` | TEXT | PK (composite with `size`) |
| `name` | TEXT | Display name |
| `size` | TEXT | PK (composite with `sku`); `S`/`M`/`L`/`XL` or `OS` |
| `qty` | INTEGER | Units available |
| `location` | TEXT | Aisle |

**Why it matters:** the Inventory agent's primary table. Stock is tracked **per SKU *and* size**, so a ticket must be checked at the size level — a SKU can look healthy in total and still be out of the one size requested.

---

### `pricing` — cost and list price
| Field | Type | Notes |
|---|---|---|
| `sku` | TEXT | PK |
| `unit_cost` | REAL | What the shop pays |
| `list_price` | REAL | What the shop charges |

**Why it matters:** the only source of margin. The Accounting agent needs it to answer discount requests (how far can list fall before the margin goes bad) and to size a purchase order from `unit_cost`.

---

### `vendors` — who can restock
| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER | PK, referenced by `invoices.vendor_id` |
| `name` | TEXT | Vendor name |
| `specialty` | TEXT | What they supply — `apparel reprint`, `mugs and small goods`, `local courier` |
| `lead_days` | INTEGER | Days from order to delivery |

**Why it matters:** Inventory picks a vendor by matching `specialty` to the SKU, and the ETA promised back to a customer is `desk.date_today + lead_days`. It also gates shipping: a vendor with an open unpaid invoice will not ship, so this table has to be read alongside `invoices`.

---

### `leases` — the shop space
| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER | PK, referenced by `tickets.lease_id` |
| `space_name` | TEXT | e.g. Chapel Street shop |
| `landlord` | TEXT | |
| `monthly_rent` | REAL | |
| `next_due` | TEXT | Next rent date |
| `notes` | TEXT | |

**Why it matters:** the Facilities agent's table. `next_due` compared against `desk.date_today` is how rent gets flagged as due or late, and `monthly_rent` is the amount that then goes to Accounting for an approval request.

---

### `cash_accounts` — the money
| Field | Type | Notes |
|---|---|---|
| `name` | TEXT | PK, currently just `checking` |
| `balance` | REAL | Funds available |
| `date` | TEXT | As-of date |

**Why it matters:** the hard constraint on the whole assignment. Cash only goes out, so `balance` is a shrinking budget every payment competes for, and the pay tool must refuse any payment that would push it negative.

---

### `payments` — the money that went out
| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER | PK |
| `kind` | TEXT | What sort of payment |
| `ref_id` | INTEGER | Points at the invoice or lease being paid |
| `amount` | REAL | |
| `account` | TEXT | → `cash_accounts.name` |
| `paid_at` | TEXT | |
| `approved_by` | TEXT | **Who approved it** |

**Why it matters:** the audit trail, and the proof that the human-approval rule was honoured — `approved_by` should never be an agent. Currently **empty**: no money has moved yet.

---

### `invoices` — what the shop owes vendors
| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER | PK, referenced by `tickets.invoice_id` |
| `vendor_id` | INTEGER | FK → `vendors.id` |
| `amount` | REAL | |
| `due_date` | TEXT | Compare to `desk.date_today` |
| `status` | TEXT | `open` / paid |
| `description` | TEXT | |

**Why it matters:** sits at the centre of the shop's one real knot. An `open` invoice is both an Accounting problem (it's overdue, it needs cash) and an Inventory problem (its vendor won't ship until it clears).

---

## Part 2 — Current contents

### desk
| date_today | notes |
|---|---|
| 2026-08-31 | *(empty)* |

### inventory
| sku | name | size | qty | location |
|---|---|---|---|---|
| CC-HOOD-NAVY | Basic Hoodie Big Yale | S | 4 | Aisle A |
| CC-HOOD-NAVY | Basic Hoodie Big Yale | M | 8 | Aisle A |
| CC-HOOD-NAVY | Basic Hoodie Big Yale | L | 14 | Aisle A |
| CC-HOOD-NAVY | Basic Hoodie Big Yale | XL | 6 | Aisle A |
| CC-TEE-WHITE | Classic Bulldog Tee | S | **0** | Aisle B |
| CC-TEE-WHITE | Classic Bulldog Tee | M | 5 | Aisle B |
| CC-TEE-WHITE | Classic Bulldog Tee | L | 3 | Aisle B |
| CC-TEE-WHITE | Classic Bulldog Tee | XL | 2 | Aisle B |
| CC-HAT-BLUE | Yale Cap | OS | 40 | Aisle C |
| CC-MUG-CREST | Crest Mug | OS | **0** | Aisle D |

### pricing
| sku | unit_cost | list_price | margin per unit |
|---|---|---|---|
| CC-HOOD-NAVY | 22.00 | 58.00 | 36.00 (62%) |
| CC-TEE-WHITE | 8.00 | 28.00 | 20.00 (71%) |
| CC-HAT-BLUE | 6.00 | 22.00 | 16.00 (73%) |
| CC-MUG-CREST | 3.50 | 14.00 | 10.50 (75%) |

### vendors
| id | name | specialty | lead_days |
|---|---|---|---|
| 1 | Bulldog Print Co | apparel reprint | 5 |
| 2 | Elm City Gifts | mugs and small goods | 3 |
| 3 | QuickShip CT | local courier | 1 |

### leases
| id | space_name | landlord | monthly_rent | next_due |
|---|---|---|---|---|
| 1 | Chapel Street shop | Elm City Properties | 2400.00 | 2026-09-02 |

### cash_accounts
| name | balance | date |
|---|---|---|
| checking | 3400.00 | 2026-08-31 |

### invoices
| id | vendor_id | amount | due_date | status | description |
|---|---|---|---|---|---|
| 501 | 1 (Bulldog Print Co) | 840.00 | 2026-08-28 | **open** | Rush reprint CC-TEE-WHITE S |

### payments
*(empty — no money has moved)*

---

## Part 3 — The three open tickets and how they link

### Ticket 101 — `customer_order` — "Bulldog tee" — Tauhid Zaman
> Needs a tee in size S.

**Links out:**
- `sku` = `CC-TEE-WHITE`, `size` = `S`, `qty` = 1 → `inventory` row **qty = 0**. Out of stock in exactly the size asked for.
- → `pricing` for `CC-TEE-WHITE`: cost 8.00, list 28.00.
- `invoice_id` = **501** → `invoices` 501, **open**, 840.00, due `2026-08-28`. Against `date_today` = `2026-08-31` that is **3 days overdue**.
- invoice 501 → `vendors` 1, **Bulldog Print Co**, specialty `apparel reprint`, **lead 5 days** — the right vendor to reprint this tee, and the vendor already owed money.

**The chain:** can't fill from stock → need a reprint from Bulldog Print Co → but they hold an open unpaid invoice, so they won't ship → so invoice 501 has to be cleared first (and that's a payment, so it needs human approval) → only then does the 5-day lead clock start. Earliest plausible ETA is `2026-08-31 + 5 days` = `2026-09-05`, and only if payment lands today. Customer Service has an ETA to draft, not a shipment to promise.

### Ticket 102 — `rent_notice` — "Rent due" — Elm City Properties
> Email: shop rent due in 2 days.

**Links out:**
- `lease_id` = **1** → `leases` 1, Chapel Street shop, landlord **Elm City Properties** (matches the requester), rent **2400.00**, `next_due` = `2026-09-02`.
- `2026-09-02` vs `date_today` `2026-08-31` = **due in 2 days**, consistent with the ticket note. Not yet late.
- → `cash_accounts.checking` for the funds.

**The chain:** Facilities confirms the lease and the amount, Accounting checks the balance covers it, and the actual payment waits on a human. No `sku`, no `invoice_id` — this ticket never touches Inventory.

### Ticket 103 — `price_override` — "Bulk hoodie discount" — Yale AI Club
> Student org wants 20 hoodies, size M, asking for a bulk discount.

**Links out:**
- `sku` = `CC-HOOD-NAVY`, `size` = `M`, `qty` = **20** → `inventory` row **qty = 8**. **Shortfall of 12 units** in size M.
- → `pricing` for `CC-HOOD-NAVY`: cost 22.00, list 58.00 — the room a discount has to fit inside.
- No `invoice_id` and no `lease_id`, but restocking the 12 would mean `vendors` 1 (`apparel reprint`, lead 5) — the same vendor blocked by invoice 501.

**The chain:** two separate questions on one ticket — *can we even supply 20?* (Inventory: no, 8 on hand) and *how low can the price go?* (Accounting: margin against 22.00 cost). Both answers feed one Customer Service draft.

### The cash squeeze linking all three
`checking` holds **3,400.00**. Invoice 501 is **840.00** and rent is **2,400.00** — together **3,240.00**, which fits, but leaves **160.00**. A reprint PO for the tee or the 12 hoodies (12 × 22.00 = **264.00**) would not fit after both. Since no revenue ever comes in, the order the agents choose to spend in is itself a decision, and it is the human who approves each step.

---

## Open questions / things to watch
- `desk.notes` is empty and `payments` is empty — both are expected starting state, not missing data.
- `tickets.status` has no enum in the schema; the vocabulary beyond `open` is ours to define in a later problem.
- `payments.kind` and `payments.ref_id` are untyped and unconstrained — `ref_id` points at either an invoice or a lease depending on `kind`, so the convention needs writing down when the pay tool is built.

---

# Problem 3 — The MCP server

Code lives in `mcp_server/` (`server.py` for the tools, `db.py` for the connection
helper). It is a FastMCP app pointed at the working copy
`data/campus_customs_new.db`; the original is never opened. All three tools in
this first set are **read-only** — the tools that move money or stock come later,
and those will carry the human-approval and no-negative-balance rules.

Two rules are enforced in the tools rather than trusted to the agents: a missing
row returns `{"found": false}` instead of a plausible guess, and anything
date-dependent reads `desk.date_today` rather than the real clock.

## The three map tools

### 1. `check_stock(sku, size)`
- **Reads:** `inventory`
- **Unlocks:** **Ticket 101** (also the supply half of 103)
- **Why it's the right tool:** Ticket 101 asks for `CC-TEE-WHITE` in size `S` and
  the tee looks fine at the SKU level with 10 units across sizes — only a lookup
  keyed on SKU *and* size reveals the `S` row sitting at **qty 0**, which is the
  fact that turns 101 from "pick it off the shelf" into a restock problem.

Returns the exact row plus `sizes_on_hand` for every size of that SKU, so the
shortfall and any substitute size land in a single call. Verified against the
working copy: `CC-TEE-WHITE`/`S` → `qty 0, in_stock false`; `CC-HOOD-NAVY`/`M` →
`qty 8` against the 20 that ticket 103 wants.

### 2. `get_lease(lease_id)`
- **Reads:** `leases` (and `desk` for the shop's date)
- **Unlocks:** **Ticket 102**
- **Why it's the right tool:** Ticket 102 is a landlord's email claiming rent is
  due in two days and carries nothing but `lease_id = 1`, so the shop's own
  record is the only way to confirm the claim — this tool resolves that id to
  the real `monthly_rent` of 2,400.00 and `next_due` of 2026-09-02, and compares
  it against `desk.date_today` so Facilities acts on the shop's ledger rather
  than on what the email asserts.

Returns `shop_today`, `days_until_due` (negative once past), and a `status` of
`overdue` / `due_today` / `upcoming`. Verified: lease 1 → `days_until_due 2`,
`status upcoming` — which corroborates the email, and shows rent is **not yet
late**.

### 3. `get_pricing(sku, qty=1)`
- **Reads:** `pricing`
- **Unlocks:** **Ticket 103**
- **Why it's the right tool:** Ticket 103 asks for a bulk discount on 20 hoodies
  and the discount cannot be judged without knowing what the shop pays — this
  tool puts `unit_cost` 22.00 against `list_price` 58.00 and extends it over the
  requested quantity, so Accounting can see the 720.00 of margin a 20-unit order
  carries and exactly how far price can fall before it hits the 22.00 floor.

Reports the room a discount has to fit inside — per-unit and extended margin,
margin percent, and `breakeven_unit_price` — but deliberately does **not** pick a
discount. That judgment is Accounting's, and anything binding is the human's.
Verified at qty 20: `extended_cost 440.00`, `extended_list 1,160.00`,
`extended_margin 720.00`, `breakeven_unit_price 22.00`.

## What these three deliberately do not cover

Each tool opens its ticket; none of them closes one. The gaps already visible
from Problem 2, to be filled by later tools:

- **Ticket 101 is gated on invoice 501**, not on stock — reading `invoices` and
  `vendors` (to apply the no-ship-while-unpaid rule and the 5-day lead time) is
  still needed before any ETA can be quoted.
- **No tool writes anything yet** — paying the invoice or the rent, cutting a
  purchase order, decrementing stock, and moving a ticket off `open` all require
  write tools with human approval in front of them.
- **Cash is unread** — `cash_accounts` has to be checked before any payment is
  proposed, since the balance is what makes the 840.00 + 2,400.00 + restock
  question a real conflict.

---

# Problem 4 — Connecting the MCP server and smoke-testing it

## Connection

`.mcp.json` at the project root registers the server for this project:

```json
{
  "mcpServers": {
    "campus-customs": {
      "command": "<project>/.venv/bin/python",
      "args": ["<project>/mcp_server/server.py"]
    }
  }
}
```

Supporting setup: a `.venv/` with **fastmcp 4.1.0** installed (pinned in
`requirements.txt`). The server advertises itself as `campus-customs` and lists
exactly three tools.

## How the test was run

The server was launched over stdio **exactly as `.mcp.json` launches it** —
same interpreter, same script path — and each tool was called through a real
MCP client session (`initialize` → `list_tools` → `call_tool`). So the evidence
is the actual MCP round trip, not a direct Python function call.

Every returned field was then checked against a fresh SQL read of
`data/campus_customs_new.db`. Full evidence, including the prompt behind each
call, lives in `output/mcp_smoke.json`.

## Results — 3/3 tools, all fields match the database

| Tool | Ticket | Key returned values | Matches DB |
|---|---|---|---|
| `check_stock(CC-TEE-WHITE, S)` | 101 | `qty 0`, `in_stock false`, Aisle B | ✅ |
| `get_lease(1)` | 102 | rent `2400.0`, due `2026-09-02`, `days_until_due 2`, `upcoming` | ✅ |
| `get_pricing(CC-HOOD-NAVY, 20)` | 103 | cost `22.0`, list `58.0`, `extended_margin 720.0` | ✅ |

`get_lease` is the one worth calling out: `shop_today` came back as
**2026-08-31**, read from `desk.date_today`, which is what makes
`days_until_due 2` correct for the shop rather than for the real calendar.

**The database was not mutated.** All three tools are read-only, and
`campus_customs_new.db` is still byte-identical to the original
(MD5 `46effb90…`) after the run.

## One caveat on "connected to the vibe coder"

`.mcp.json` is read when a Claude Code session **starts**, and a project-scoped
server also needs a one-time approval. The file was written during this session,
so the tools are not in this session's tool list yet — restarting the session in
this folder and approving `campus-customs` makes them callable as
`mcp__campus-customs__check_stock` and friends. The smoke test above does not
depend on that: it drove the server through the MCP protocol directly.

---

# Problem 5 — The agent team, the full tool set, and the guardrails

## The team

Five PydanticAI agents, all on **gpt-6-luna through Portkey** (fixed in
`backend/config.py`; `build_model()` takes no model argument, so no other model
can reach the API). Each agent's prompt is its own file in `backend/prompts/`,
spliced with `_shared_rules.md` — the rules every agent needs — at build time.

| Agent | File | Prompt | Owns | Returns |
|---|---|---|---|---|
| **Boss** | `backend/agents/boss.py` | `prompts/boss.md` | Reads each ticket, routes it, makes the final call, closes it | `TicketVerdict` |
| **Inventory** | `backend/agents/inventory.py` | `prompts/inventory.md` | Stock by SKU **and** size, shortfalls, which vendor can restock and when | `AgentReport` |
| **Accounting** | `backend/agents/accounting.py` | `prompts/accounting.md` | Cash, invoices, margins; writes the approval requests a human decides from | `AgentReport` |
| **Facilities** | `backend/agents/facilities.py` | `prompts/facilities.md` | The lease, the landlord, rent timing; verifies notices against the shop's own record | `AgentReport` |
| **Customer Service** | `backend/agents/customer_service.py` | `prompts/customer_service.md` | Drafts customer messages — never sends | `AgentReport` |

**Full connectivity.** Every agent gets one `ask_teammate` tool that can reach
any of the other four. Nothing in the wiring privileges the Boss; only its
prompt says routing is its job. A live run of ticket 101 produced
`inventory → accounting` at depth 2 — a specialist delegating to another
specialist without going back through the Boss.

Supporting modules: `backend/models.py` (data types), `backend/config.py` (model
+ MCP wiring + limits), `backend/team.py` (agent construction, delegation,
traced loops), `backend/audit.py` (append-only trail), `backend/runner.py` (works
a ticket or the whole board), `backend/mcp_tools.py` (direct MCP calls for
orchestration code that needs a fact without paying for a model call).

## Every MCP tool and the table it uses

26 tools on one server over `data/campus_customs_new.db`. Agents see them
prefixed `campus-customs_`.

| Tool | Tables used | Why the team needs it |
|---|---|---|
| `get_shop_date` | `desk` | The shop's clock; every due/overdue call keys off it |
| `list_tickets` | `tickets` | The board |
| `get_ticket` | `tickets` + `inventory`, `pricing`, `leases`, `invoices`, `vendors` | One call gives the Boss the ticket and every record it points at |
| `update_ticket` | `tickets` | Records where a ticket landed, appending to its history |
| `check_stock` | `inventory` | Stock at the SKU **and size** level, plus sibling sizes |
| `check_shortfall` | `inventory` | Wanted vs on hand — keeps the arithmetic out of the model |
| `get_pricing` | `pricing` | Cost, list, margin at a quantity |
| `quote_discount` | `pricing` | Scores a proposed price; flags at-or-below cost |
| `adjust_inventory` | `inventory` | Moves stock that really moved; refuses to go below zero |
| `list_vendors` | `vendors` | Specialties and lead times |
| `find_vendor_for_sku` | `vendors` + `invoices` | Who can supply a SKU, ETA, and whether they are blocked |
| `check_vendor_can_ship` | `vendors` + `invoices` + `desk` | The no-ship-while-unpaid rule, what blocks, what it costs to unblock |
| `get_cash_balance` | `cash_accounts` + `approvals` | Balance **and** what is already queued against it |
| `list_invoices` | `invoices` + `vendors` + `desk` | Open/paid invoices with days overdue |
| `get_lease` | `leases` + `desk` | Rent, due date, overdue / due today / upcoming |
| `list_payments` | `payments` | Every payment, with the human who approved it |
| `request_approval` | `approvals` | The only way an agent moves toward spending |
| `list_approvals` | `approvals` | What is waiting on a person |
| `record_human_decision` | `approvals` | **The human's tool** — approve or reject, by name |
| `pay_invoice` | `payments`, `invoices`, `cash_accounts`, `approvals` | Settles an invoice; also what unblocks a vendor |
| `pay_rent` | `payments`, `leases`, `cash_accounts`, `approvals` | Pays rent; rolls `next_due` forward |
| `place_purchase_order` | `payments`, `cash_accounts`, `approvals`, `vendors`, `pricing` | Turns an approved purchase order into a real order: pays the vendor, returns the arrival date, leaves stock alone until goods land |
| `apply_price_override` | `approvals`, `pricing` | Puts an approved discount into effect so it can be quoted; moves no money |
| `save_draft_message` | `drafts` | Customer message saved `draft_not_sent` |
| `list_drafts` | `drafts` | Drafts waiting for review |
| `reset_shop_database` | all | Restores the working copy from the pristine original |

`approvals` and `drafts` are created by the server itself (`CREATE TABLE IF NOT
EXISTS`) and rebuilt after a reset. Keeping them in the same file means there is
still one source of shop truth.

## The audit trail

`output/audit_trail.json` is a JSON array, **appended to and never wiped** — a
new run adds its events after the last run's, written through a temp file so a
crash cannot truncate the history. One event per agent-loop node, carrying
`run_id`, `seq`, `ts`, `shop_date`, `ticket_id`, `agent`, `parent_agent`,
`depth`, `step`, `kind`, `model`, `text`, `tool_calls` (with arguments),
`tool_returns` (clipped), and `usage`.

Two live runs are recorded: ticket 101 (43 events, boss + inventory +
accounting + customer service, 4 delegations) and ticket 102 (39 events, boss +
facilities + accounting). Both runs survive in the file.

## Safety — what a real business would want

**Money cannot move without a named human.** `pay_invoice` and `pay_rent` refuse
unless an `approvals` row for that exact kind, target, and amount is `approved`
and carries a person's name in `decided_by`; that name is copied into
`payments.approved_by`. The gate is in the tool, not in a prompt, because a
prompt is a request and a tool is a rule. An agent that decided to pay anyway
would simply get a refusal.

**Separation of duties.** Agents may only *request*; `record_human_decision` is
the human's tool and every prompt says so. The agent that asks for money is not
the one that releases it.

**No negative balances, no partial payments.** A payment larger than the balance
is refused outright rather than partially applied. The same rule guards the
shelf: `adjust_inventory` will not take stock below zero.

**Idempotency.** An invoice cannot be paid twice, an approval cannot be executed
twice, a decided request cannot be re-decided, and a duplicate pending request is
rejected with a pointer to the original. Retries are the normal failure mode for
an agent loop, and without these a retry is a second payment.

**Nothing reaches a customer or a vendor.** There is no send tool and no mail
client. Messages land in `drafts` as `draft_not_sent` for a person to review.
The capability does not exist, so it cannot be misused.

**Every refusal explains itself.** Tools return a `refused` code and a message
describing what is true about the shop, so an agent reports the obstacle rather
than retrying with different arguments until something works.

**One clock.** `desk.date_today` is the only "now". An agent that used the real
date could declare rent overdue and push the shop to spend early.

**One data path.** Agents reach the shop only through the MCP server, loaded
from the same `.mcp.json` the editor uses. No agent holds a database handle, so
the guardrails cannot be stepped around.

**Full provenance.** Every tool call, its arguments, and its result are in the
audit trail against a `run_id`, so any payment can be traced back to the
reasoning and the approval that produced it.

### What is still missing for real money
Honest gaps, not claims: no authentication on the approving human's identity
(`decided_by` is a string the dashboard supplies); no per-day or per-ticket
spend ceiling in the tools; no second approver for large amounts; no immutable
log (the audit file is writable); approvals do not expire; and nothing
rate-limits how often the team can be run.

## Limits that keep token use in check

Set in `backend/config.py` and enforced in `backend/team.py`:

| Limit | Value | What it stops |
|---|---|---|
| `MAX_REQUESTS_PER_AGENT` | 8 | A single agent looping forever on its own |
| `MAX_TOOL_CALLS_PER_AGENT` | 20 | Tool-call thrash inside one loop |
| `MAX_DELEGATION_DEPTH` | 2 | Infinite hand-off chains (A asks B asks A …) |
| `MAX_DELEGATIONS_PER_TICKET` | 6 | Breadth — the whole team consulting itself in circles |
| `TOOL_RESULT_CLIP` | 1200 chars | An unbounded tool result bloating the trail |

The delegation budget is **shared across the whole ticket**, not per agent: a
hand-off two levels down still spends the same allowance, so breadth and depth
cannot be combined to escape it. When a limit is hit the tool returns a message
telling the agent to finish with what it has, rather than raising — the run ends
with a usable answer instead of an exception.

Prompt-side, every agent is told not to re-read a table it has already read, not
to survey the database, and to stop calling tools once it can answer. The
measured cost of the ticket-101 run was 16 model requests, ~81k input tokens
(29k of them cached) and ~3.6k output tokens for a four-agent collaboration.

---

# Problem 7 — Backend routes

`backend/main.py`, started from the `backend/` folder:

```bash
uvicorn main:app --reload --port 8000
```

The API opens no database of its own. Every route calls the same campus-customs
MCP tools the agents call, so a click in the dashboard is bound by the same
guardrails as an agent action. Interactive docs come free at
`http://localhost:8000/docs`.

## The routes

| Route | What it does |
|---|---|
| `GET /` | What the service is, which model it runs, the shop's date, and the route list |
| `GET /tickets` | All three tickets with `status`, `is_open` and `is_resolved`, plus open/resolved counts |
| `POST /tickets/{ticket_id}/run` | Runs the agent team on one ticket; returns the Boss's verdict, every delegation, and token usage. Can create approval requests — **never** moves money. Optional `{"reset_first": true}` |
| `GET /events` | Recent agent activity — what each agent said and which tools it used, with arguments. Supports `?after_id=` for incremental polling, plus `?ticket_id=` and `?run_id=` filters |
| `GET /approvals` | Requests the agents prepared for a human, so the board can render approve buttons. `?status=all` for history |
| `POST /approvals/{approval_id}/approve` | **The only route that moves cash.** Records the human's decision by name, then settles it — `pay_invoice` or `pay_rent` — and returns the outcome including any refusal |
| `GET /cash` | Checking balance from `cash_accounts`, what is already queued against it, and what would be left if everything pending were paid |
| `POST /reset` | Restores the working copy from the pristine original for a fresh run |

`GET /approvals` is not on the original list but the approve route is unusable
without it — a request has to be visible before a human can click it.

## Where the human/agent line sits

`POST /tickets/{id}/run` and `POST /approvals/{id}/approve` are deliberately
separate routes. The first is the agents working; the second is a person
releasing money. Nothing an agent does inside a run can reach the second.

## Verified end to end

Started with `uvicorn main:app --reload --port 8000` and exercised every route:

| Check | Result |
|---|---|
| `POST /reset` → `GET /tickets` | 3 open, balance restored to 3,400.00 |
| `POST /tickets/101/run` | `waiting_approval`, consulted inventory + accounting + customer service, 4 delegations including `inventory → accounting` at depth 2, approval 1 created |
| `GET /events?ticket_id=101` | 174 events total, each with agent, depth, kind, what was said, and tools used with arguments |
| `GET /approvals` | Approval 1 pending, $840, requested by accounting, with its full rationale |
| `POST /approvals/1/approve` | **Cash moved 3,400.00 → 2,560.00**, payment 1 written with `approved_by: Julian`, Bulldog Print Co unblocked |
| Approve the same request twice | `409` — already executed |
| `POST /tickets/999/run` | `404` |
| Approve with a blank name | `422` — the approver must be named |
| Approve rent with only 160.00 left | `money_moved: false`, `refused: insufficient_funds`, `short_by: 2240.00`, balance unchanged |
| `POST /reset` afterwards | Shop back to 3,400.00 and 3 open tickets; **audit trail kept all 174 events** |

A reset clears the shop but not the trail — the run history is append-only on
purpose, so a reset cannot erase evidence of what the agents did.

One ticket runs at a time, guarded by a lock; a second concurrent run gets a
`409` rather than racing on the same balance.

---

# Problem 8 — The dashboard

`frontend/` — React + Vite + TypeScript, started with `npm run dev` on
`http://localhost:5173`. It calls the Problem 7 backend on
`http://localhost:8000`, which already allows that origin via CORS. Design
reasoning lives in `output/design.md`.

Three columns, each with one job: **The Board** (tickets), **The Floor** (five
agent lanes, the Boss's verdict, the live step stream), **The Ledger** (checking
balance and the approval queue). The middle column cannot move money; only the
right one can. That is the human/agent boundary drawn as layout.

Verified in the browser: ran the team on 101 and 102, watched lanes and stream
fill live, then approved a payment and saw checking fall 3,400 → 2,560 with the
depletion meter and drop animation following. Three bugs found and fixed during
that testing — a verdict card wiped on run completion, loaded history mixing
every past run of a ticket, and StrictMode's double-mounted poller doubling the
per-agent step counts.


---

# Problem 9 — The full run

One continuous pass over the board, starting from `reset_shop_database`. Driven
by `backend/full_run.py`, which runs each ticket, acts as the human on whatever
the team puts up for approval, and runs it again so the Boss can close it —
every step through the same FastAPI routes and the same MCP tools the dashboard
uses.

**Opening balance: $3,400.00. Closing balance: $160.00.**

## What happened

| Ticket | Final | Passes | Agents | Hand-offs | Cash |
|---|---|---|---|---|---|
| **101** — Bulldog tee | `resolved` | 2 | Boss, Inventory, Accounting, Customer Service | 4 | $-840.00 |
| **102** — Rent due | `resolved` | 2 | Boss, Facilities, Accounting | 3 | $-2,400.00 |
| **103** — Bulk hoodie discount | `blocked` | 2 | Boss, Accounting, Inventory, Customer Service | 3 | — |

Two tickets resolved. The third is `blocked`, and that is the honest answer
rather than a failure: the shop cannot supply it and cannot afford to try.

### 101 — Bulldog tee
Size S was empty, and the vendor who could reprint it was frozen by an unpaid
invoice. Accounting put the $840.00 invoice up, a human approved it, and paying
it unblocked Bulldog Print Co. The ticket's linked invoice — `Rush reprint
CC-TEE-WHITE S` — *was* the restock, so Inventory correctly declined to order the
same goods twice and quoted the vendor's five-day lead time as an estimate
instead. Customer Service drafted an honest update. **Resolved.**

### 102 — Rent due
Facilities checked the landlord's notice against lease 1 and confirmed
$2,400.00 due 2026-09-02 — upcoming, two days out, **not** late. Accounting put
it up against a balance that had just lost $840.00; a human approved; rent was
paid and `next_due` rolled forward. **Resolved.**

### 103 — Bulk hoodie discount
The club wanted 20 size-M hoodies and named no price. Accounting proposed the
shop's own offer — $52 a unit, 10.3% off the $58 list, leaving $30 of margin —
and a human approved it. But only 8 of the 20 exist, and restocking the other 12
costs $264.00 against a balance of $160.00. **The shop is $104.00 short, so no
order was placed.** The discount was applied to the 8 that exist and a draft went
to the board without promising the rest. **Blocked** — by cash, which is exactly
the constraint the assignment set.

## The cash, itemised

| | Change | Balance |
|---|---|---|
| Opening, after reset | — | $3,400.00 |
| Ticket 101 — invoice 501 to Bulldog Print Co, approval #1 | −840.00 | $2,560.00 |
| Ticket 102 — September rent on lease 1, approval #2 | −2,400.00 | $160.00 |
| Ticket 103 — discount approved, **no money moved** | 0.00 | $160.00 |
| **Closing** | **−3,240.00** | **$160.00** |

$3,400.00 − $3,240.00 = **$160.00**, which is `cash_accounts.balance` in
`data/campus_customs_new.db`. `backend/build_desk_tabs.py` asserts this against
the database before it will write the page, so the board cannot disagree with
the shop.

Both payments carry **Julian** in `payments.approved_by`. No agent wrote that
column, and none could.

## What the run proved about the guardrails

- **Nothing was paid without a human.** Four approvals were raised; every one was
  decided by a named person before any tool moved money.
- **The no-negative-balance rule bit, and held.** Ticket 103's restock was
  refused on cash. The team reported the shortfall rather than finding a way
  around it.
- **No vendor shipped while owed money.** 101's whole sequence exists because
  `check_vendor_can_ship` reported `false` until invoice 501 cleared.
- **Nothing was sent.** Every customer message is a `draft_not_sent` row.
- **The clock held.** Rent was reported as upcoming, not overdue, because
  `desk.date_today` is 2026-08-31 and `next_due` is 2026-09-02.

## Faults this run exposed, and what fixed them

The first attempts did not go cleanly. Each failure was a gap in this build, not
a model error, and each is worth recording:

| Fault | Cause | Fix |
|---|---|---|
| Boss hit its request limit on a second pass | 8 calls was fine for a fresh ticket, too tight for one with history | Per-role limits: 16 for the Boss, 10 for specialists |
| An approved purchase order did nothing | `request_approval` could raise a PO, but **no tool could execute one** | Added `place_purchase_order` |
| An approved discount did nothing | Same gap again, for `price_override` | Added `apply_price_override` |
| Boss sent 101 to a human repeatedly | `tickets.invoice_id` encodes that the invoice serves the ticket — and no prompt ever said so, so the team would not rely on it | `get_ticket` now returns `restock_already_ordered` and `link_explained` as facts |
| A price override was approved but unusable | Accounting put the price in the subject line and left `amount` null | `request_approval` now refuses any request without an amount |
| An unexecutable approval could not be cleared | No way for a human to withdraw something already approved | Added `cancel_approval` |
| One ticket lost to a network blip | Driver treated any failed pass as terminal | Retries transient provider errors, 3× with backoff |

The pattern in the middle four is the same: **a human could approve something the
shop had no way to carry out.** Every approval kind now has exactly one tool that
executes it — `pay_invoice`, `pay_rent`, `place_purchase_order`,
`apply_price_override` — and a way to withdraw it if it cannot be.

A slower lesson sits behind the 101 failure. The rule "never assert what the
tools do not establish" worked *too* well: the agents refused to act on a
relationship the schema encoded but the prompts never explained. The fix was
never to loosen the rule — it was to make the fact available. That is the right
trade when money is involved.

## Where the outputs are

| File | What |
|---|---|
| `output/desk_tickets.html` | Expected vs **Actual** per ticket, plus the itemised Cash tab |
| `output/resolved_tickets.json` | Per ticket: id, final status, outcome, each agent's contribution, human approvals |
| `output/resolved_board.html` | The dashboard captured for each ticket |
| `output/audit_trail.json` | Every agent-loop step across every run, appended never wiped |
| `output/full_run_log.json` | The raw driver log this write-up is built from |

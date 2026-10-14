# Campus Customs MCP Server

## What it is for

This is the single door between the Campus Customs agent team and the shop's
database. The Boss, Inventory, Accounting, Facilities, and Customer Service
agents have no direct SQL access — everything they know about stock, money,
leases, and vendors arrives through the tools defined here. That keeps the
shop's rules in one enforceable place instead of scattered across five agents'
prompts.

Two rules are baked into the tools rather than left to the agents:

- **Never invent data.** A tool reports what the database holds. If a row is
  missing it returns `{"found": false, ...}` with a message, so an agent cannot
  mistake a guessed quantity or price for a real one.
- **The shop's clock is `desk.date_today`**, not the real system date. Anything
  that decides what is due or overdue reads that field.

## Which database it uses

`data/campus_customs_new.db` — the **working copy**.

`data/campus_customs.db` is the pristine original and is never opened by this
server. To reset the shop to its starting state, copy the original over the
working copy:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

The path is resolved in `db.py` relative to the project root, so the server can
be started from any directory.

## The tools

All 26 tools are on one server, so every agent sees the same shop. Tool names
reach the agents prefixed with the server name, e.g.
`campus-customs_check_stock`.

### Reading the board

| Tool | Tables | What it answers |
|---|---|---|
| `get_shop_date` | `desk` | What "today" is for the shop |
| `list_tickets` | `tickets` | What is on the board |
| `get_ticket` | `tickets` + `inventory`, `pricing`, `leases`, `invoices`, `vendors` | One ticket with every record it points at, resolved |
| `update_ticket` | `tickets` | Move a ticket's status and append a dated note |

### Stock and price

| Tool | Tables | What it answers |
|---|---|---|
| `check_stock` | `inventory` | Units of one SKU in one size, plus every other size |
| `check_shortfall` | `inventory` | Wanted vs on hand, and the gap — arithmetic the model never does |
| `get_pricing` | `pricing` | Cost, list, and margin at a quantity |
| `quote_discount` | `pricing` | What a proposed price does to margin; flags at-or-below cost |
| `adjust_inventory` | `inventory` | Move stock in or out; refuses to go below zero |

### Vendors

| Tool | Tables | What it answers |
|---|---|---|
| `list_vendors` | `vendors` | Every vendor, specialty, lead time |
| `find_vendor_for_sku` | `vendors` + `invoices` | Which vendors can supply a SKU, their ETA, and whether they are blocked |
| `check_vendor_can_ship` | `vendors` + `invoices` + `desk` | The no-ship-while-unpaid rule, what is blocking, and what it costs to unblock |

### Money — reading

| Tool | Tables | What it answers |
|---|---|---|
| `get_cash_balance` | `cash_accounts` + `approvals` | Balance, what is already queued against it, what would be left |
| `list_invoices` | `invoices` + `vendors` + `desk` | Open or paid invoices with days overdue |
| `get_lease` | `leases` + `desk` | Rent, due date, and overdue / due today / upcoming |
| `list_payments` | `payments` | Every payment made, with the human who approved it |

### Human approval

| Tool | Tables | What it answers |
|---|---|---|
| `request_approval` | `approvals` | An agent asks a human for permission to spend or discount |
| `list_approvals` | `approvals` | What is waiting on a person |
| `record_human_decision` | `approvals` | **The human's tool.** Approve or reject, by name |

### Money — movements

| Tool | Tables | What it answers |
|---|---|---|
| `pay_invoice` | `payments`, `invoices`, `cash_accounts`, `approvals` | Settle an invoice — only on a matching human approval and sufficient cash |
| `pay_rent` | `payments`, `leases`, `cash_accounts`, `approvals` | Pay one month's rent, same gates; rolls `next_due` forward |

### Executing what a human approved

| Tool | Tables | What it answers |
|---|---|---|
| `place_purchase_order` | `payments`, `cash_accounts`, `approvals`, `vendors`, `pricing` | Places an approved restock order — pays the vendor, returns the expected arrival, and deliberately does **not** raise stock (the goods are in transit) |
| `apply_price_override` | `approvals`, `pricing` | Puts an approved discount into effect so Customer Service can quote it. No money moves — a price is what the shop charges |

An approval is a decision, not an action. Every approval kind has exactly one
tool that carries it out: `pay_invoice`, `pay_rent`, `place_purchase_order`,
`apply_price_override`. Without that pairing an approved request would sit
forever with a human having said yes and nothing having happened.

### Customer drafts

| Tool | Tables | What it answers |
|---|---|---|
| `save_draft_message` | `drafts` | Save a customer message as `draft_not_sent`. **There is no send tool.** |
| `list_drafts` | `drafts` | Drafts waiting for a person to review |

### Admin

| Tool | Tables | What it answers |
|---|---|---|
| `reset_shop_database` | all | Restore the working copy from the pristine original |

## Two tables this server creates

`approvals` and `drafts` are not in the original shop file. The server creates
them with `CREATE TABLE IF NOT EXISTS` on every connection, and recreates them
after a reset. They hold the workflow state the agents produce — requests
waiting on a human, and messages that must never be sent — in the same database
as everything else, so there is still exactly one source of shop truth.

## How the money rules are enforced

Not by asking the agents nicely:

- `pay_invoice` / `pay_rent` refuse unless an `approvals` row for that exact
  kind, target, and amount is in `approved` status with a named human in
  `decided_by`. That name is what lands in `payments.approved_by`.
- They refuse any amount larger than the balance. No partial payments, no
  negative balances.
- They refuse to settle the same thing twice.
- `record_human_decision` refuses a blank approver and refuses to re-decide a
  request that is already decided.
- `adjust_inventory` refuses to take a shelf below zero.

Every refusal returns a `refused` code and a message explaining what is true
about the shop, so the agent reports the obstacle instead of retrying blindly.

## Running it

```bash
.venv/bin/python mcp_server/server.py
```

Registered for this project in `.mcp.json` at the repository root, which is also
the file the agent team loads its toolset from — there is no second wiring.

## Files

- `server.py` — the FastMCP app and all 26 tools
- `db.py` — connection helper, workflow-table schema, the `desk.date_today`
  lookup, date arithmetic, and the reset

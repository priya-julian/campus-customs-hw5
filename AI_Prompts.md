# AI Prompts Log — Homework 5: Campus Customs Multi-Agent Operations

A log of what I typed into the vibe coder while building this assignment.
One section per problem. Typos cleaned up, wording otherwise kept as I wrote it.

---

## Setup (before Problem 1)

**Prompt:**

> In HW5 we will build Campus Customs multi-agent operations. It's the agentic team that runs the shop. Open tickets land on a board — customer orders, rent, unpaid bills, discount requests, whatever the shop has to handle. We will build 3 pieces that talk to each other: an MCP server, a FastAPI backend with a multi-agent team, and a React dashboard so a human can watch the agents at work and approve requests.
>
> Our agent team has full connectivity — any agent may delegate tasks to any other agent for help. We will build these agents: Boss (reads each ticket, decides who should work on it, and makes final calls), Inventory (checks stock by SKU and size, spots shortfalls, and figures out which vendor can restock), Accounting (watches cash and invoices, checks margins, and prepares payments or purchase orders for human approval), Facilities (handles the shop space side like leases, rent, etc.), Customer Service (drafts messages for customers).
>
> We should see `data/campus_customs.db`. That file is the original shop database. Tables include desk, tickets, inventory, pricing, vendors, leases, cash accounts, payments, and invoices. Your tools will update the database as tickets get resolved. Make a copy of the database file called `data/campus_customs_new.db` and point the MCP server and backend at that working copy. Keep `campus_customs.db` untouched so I can reset when I want to start resolving the tickets.
>
> Rules of the shop:
> - The field `desk.date_today` is "today" for the shop. Use this date to determine what is overdue.
> - Vendor lead times come from the vendors table.
> - A vendor will not ship new product while they still have an open unpaid invoice.
> - Human approval is required for any payments — points will be deducted if this is not done. If payment is made, make sure to update the relevant table.
> - If there is not enough cash, the pay tool must refuse — no negative balances.
> - Cash only goes out in this HW — we did not model revenue, so no money comes in.
> - Before a full run to resolve the tickets, make sure to reset the database to the original values.
> - Do NOT email customers or call real vendors. Drafts stay on the board.
>
> Use my `PORTKEY_API_KEY` for AI calls. For this assignment use ONLY `gpt-6-luna` through Portkey for every agent. Points will be deducted if any other model shows up in the code or runs.
>
> Okay — so don't do anything right now. All of what I wrote above was just setup, so remember it as we work together. Ready to go?

**What this established:** the whole build (MCP server + FastAPI multi-agent backend + React dashboard), the five agents and their full-connectivity delegation, the database copy rule, the shop rules, and the model restriction.

---

## Problem 1: Vibe Coder Prompts

**Prompt:**

> Problem 1: vibe coder prompts. Create `AI_Prompts.md` at the start of the assignment and keep it updated as we work. This file is a log of what I typed into the vibe coder. Put one section for each problem. Each section must include: problem number and title, at least one prompt I typed in my own words as much as possible (please clean it up a bit, like with typos), one follow-up prompt if needed (and one sentence on what was lacking after the first). Got that?

**Follow-up prompt:** none needed yet.

**Status:** file created. It will be updated as each remaining problem is worked.

---

## Problem 2: Study the Campus Customs Database

**Prompt:**

> Problem 2: Study the Campus Customs database. Open `data/campus_customs.db` and look through every table and its fields. Copy the original file to `data/campus_customs_new.db` (later problems update that working copy). Study the 3 open tickets so you see how they link to other tables. Start `output/harness.md`. For each table, list the fields and one short line on why that table matters for the agents. We will keep growing this harness file in later problems. Make these things easy for me to open and look over myself. Please don't work ahead.

**Follow-up prompt:** none needed.

**Status:** done. Working copy created and verified identical to the original; `output/harness.md` now holds the field-by-field table map, a full snapshot of current contents, and a walkthrough of how each of the 3 open tickets links to the other tables.

---

## Problem 3: Build the MCP Server

**Prompt:**

> Problem 3: Build the MCP server. Write an MCP server in `mcp_server/` using FastMCP. It will talk to `data/campus_customs_new.db`. You do not need to connect or run it in this problem. Every agent in this HW uses the tools in this MCP server. You will add more tools to it later; for now write three tools you know you will need for the tickets in the database. Keep the names clear, never invent any data, only use info in the database.
>
> In `output/harness.md`, list each of your 3 map tools. For every tool include which table it reads, which ticket it helps unlock (101, 102, or 103), and in ONE sentence why that tool is the right one for that ticket — vague lines like "Reads inventory" score low, tie the tool to the ticket. Also add a short `mcp_server/README.md` file that explains what the MCP server is for, which database file it uses, and the three tools it has.

**Follow-up prompt:** none needed.

**Status:** done. `mcp_server/server.py` (FastMCP, three read-only tools: `check_stock`, `get_lease`, `get_pricing`), `mcp_server/db.py` (working-copy connection, `desk.date_today` lookup, date math), `mcp_server/README.md`, and a new Problem 3 section in `output/harness.md` tying each tool to its ticket.

---

## Problem 4: Add the MCP Server to the Vibe Coder and Test Each Tool

**Prompt:**

> Problem 4: Add the MCP server to the vibe coder and test each tool. Add my MCP server to this project so you as my vibe coder can call the tools. Save the connection JSON text in `.mcp.json` at the project root (or however Claude Code saves local MCP server lists). With this vibe coder connected, test each of the 3 MCP tools. Save the evidence in `output/mcp_smoke.json`. For every tool please include: the prompt you asked the vibe coder, the tool name, and the tool output (must match values in `data/campus_customs_new.db`).
>
> So you as my vibe coder can do all of the connecting and testing yourself, right? Or do you need more from me right now?

**Follow-up prompt:** none needed — but note the one thing I had to be told back: `.mcp.json` is only read when a Claude Code session starts, so the tools do not appear in the current session until it is restarted and the server approved. The smoke test was run by driving the server over the MCP protocol directly, which does not depend on that.

**Status:** done. Created `.venv` with fastmcp 4.1.0 (`requirements.txt`), wrote `.mcp.json` at the project root, launched the server over stdio exactly as that config does, and called all three tools through a real MCP client session. Evidence in `output/mcp_smoke.json`: 3/3 tools, every field verified against a fresh SQL read of the working copy, database unmutated.

---

## Problem 5: Build the Agent Team and Grow the MCP Tools

**Prompt:**

> Problem 5: Build the agent team and grow the MCP tools. Build the agentic team for Campus Customs using PydanticAI: Boss, Inventory, Accounting, Facilities, and Customer Service. Include prompts, models, and agent loops so they can delegate work to each other with full connectivity. Put the agent prompts in `backend/prompts/` — one file per agent. Put data types in `backend/models.py` and the agent files under `backend/` (the five roles must be clear). Use my `PORTKEY_API_KEY` and only `gpt-6-luna` for every agent. Write each prompt in your own words with the shop rules that the agent needs. More detailed prompts that cover all aspects of an agent's work and scope will get more points than a short generic prompt. Add any tools the agents need to the MCP server so they can work on the open tickets. Shop facts come from the MCP server over `data/campus_customs_new.db` — do not invent a second shop-tools layer that bypasses MCP. Wire the agents so they append to `output/audit_trail.json` as they run: for each agent-loop step, record enough to audit later. Append to this file — do not wipe it each run.
>
> In `output/harness.md` list each agent and each MCP tool (including ones you add in this problem) along with which table the tool uses. Also add a short safety section: the guardrails a real business would want when agents touch real customers and real money, plus limits that keep token use in check. Update `mcp_server/README.md` so the tool list matches what you have now.
>
> Need anything else from me?

**Follow-up prompt:** none needed.

**Status:** done. Five agents on gpt-6-luna via Portkey, fully connected through one `ask_teammate` tool; MCP server grown from 3 to 24 tools; append-only audit trail. Verified with two live runs (tickets 101 and 102) plus a guardrail test suite proving payments refuse without human approval, refuse on insufficient funds, and refuse to pay twice.

---

## Problem 6: Plan the Three Tickets

**Prompt:**

> Problem 6: Plan the three tickets. Before you wire the backend, write down what you expect the team to do on each open ticket. Build `output/desk_tickets.html` — a page you can double-click, with one tab per ticket (101, 102, 103). Also add empty Cash and Reflection tabs for later problems (leave them blank or with a short "coming later" note for right now). On each ticket tab, fill an Expected section only (leave room for an Actual section you will fill after you run the agents).
>
> For each ticket's Expected section write in your own words: who the Boss should call first and why, all the agent delegations you expect — not "Boss calls everyone" — and which MCP tools you expect that run to use. Plans that send every specialist on every ticket score low. Essentially you want to be efficient and effective. You will compare this plan to what actually happens when your agents resolve the three tickets. Got it?

**Follow-up prompt:** none needed — but I flagged back that three exploratory runs had already happened in Problem 5, so these expectations are informed reasoning rather than a blind forecast, and the Actual sections will be filled from a clean reset run.

**Status:** done. `output/desk_tickets.html` is a standalone page (no dependencies, double-click to open) with five tabs. Each ticket tab names the first call and the reasoning behind it, every delegation hop I expect with a justification, an explicit "who should NOT be involved" note, a table of expected MCP tools per agent, the expected disposition, and the trap to watch for. Cash and Reflection are stubbed for later.

---

## Problem 7: Backend Routes

**Prompt:**

> Problem 7: Backend routes. Your React frontend dashboard (the next problem, so don't work ahead) needs a backend it can call. In `backend/main.py`, use FastAPI and add routes that do the following: return the three tickets and whether each is open or resolved; take a ticket id and run your agent team on that ticket; return recent agent events — what each agent said and which tools they used — so the board can refresh; approve a payment or purchase after a human clicks approve (agents only prepare the pay, this route is what actually changes cash); return the current checking balance from `cash_accounts`; reset the database to the original values when you want to try a fresh run.
>
> From the `backend/` folder, start the server with: `uvicorn main:app --reload --port 8000`. This turns on your backend at `http://localhost:8000` so the frontend dashboard can call those routes. In `output/harness.md`, list each route in one line (what URL / what it does).
>
> Sound good?

**Follow-up prompt:** none needed.

**Status:** done. `backend/main.py` serves the six requested routes plus `GET /` and `GET /approvals` (the approve route is unusable without a way to list what is pending). Verified live with uvicorn on port 8000: a real agent run through HTTP, a human approval that moved cash 3,400 → 2,560 with the payment recorded against the approver's name, and the refusal paths — double approval, unknown ticket, blank approver, and insufficient funds — all returning correctly without moving money.

---

## Problem 8: Agent Dashboard

**Prompt:**

> Problem 8: Agent dashboard. Build the frontend dashboard in `frontend/` with React + Vite + TypeScript. The page should call the routes you built in Problem 7. At minimum the board should: list all three tickets; let you pick one ticket and start the agent team on it; show each agent and what they are saying/doing while the ticket runs; mark a ticket resolved when the run finishes; show a short summary of what each agent did on that ticket; let a human approve a pay or purchase when asked; show the checking balance (it should drop after an approved pay).
>
> Make the dashboard look good. Be creative with the layout and feel — this is a real desk people would want to sit at, so put thought into how it looks. Go for a professional, clean vibe that's easy to read. Use fun shades of blue to make it more interesting.
>
> Tell the frontend to talk to your backend at `http://localhost:8000`. On the backend, allow the Vite page origin (usually `http://localhost:5173`) so the browser is allowed to call those routes. Start the board with `npm run dev` — this opens the React desk in your browser so you can pick tickets and watch agents.
>
> Write `output/design.md` with what you chose for the dashboard look (layout, how agents read differently, how resolved tickets and cash show up) and why — including the creative choices that make it feel special and something humans would actually enjoy using.

**Follow-up prompt:** none needed.

**Status:** done. Three-column desk — Board / Floor / Ledger — driven entirely by the Problem 7 routes. Verified in the browser end to end: ran the team on tickets 101 and 102, watched the lanes and stream fill live, then approved a payment and saw checking fall 3,400 → 2,560 with the meter and the drop animation. Fixed three real bugs found during that testing: the verdict card was wiped when a run ended, loaded history mixed every past run of a ticket together, and StrictMode's double-mounted poller was doubling the per-agent step counts.

---

## Problem 9: Resolve the Tickets

**Prompt:**

> Problem 9: Resolve the tickets. Before testing the agents on a full run over all three tickets, reset the working database `data/campus_customs_new.db` again so you start clean. Note the starting checking balance. Then run all three tickets on the board (101, 102, 103) until each is resolved. Open `output/desk_tickets.html` from Problem 6. On each ticket tab, fill the Actual section from this run: which agents worked, what they delegated, and which tools they used. Keep your Expected section so you can compare the two. On the Cash tab of the same `output/desk_tickets.html`, itemize the money: starting checking balance (after the reset); for each ticket, how cash changed when that ticket resolved and why (which pay/purchase, dollar amount); ending checking balance — it must match `cash_accounts` in the working database.
>
> Wrong cash math will lose points even if the board shows every ticket resolved, so be careful with the numbers. Also save `output/resolved_tickets.json` — for each ticket: id, final status, short outcome, what each agent contributed, and any human approvals — and `output/resolved_board.html`, a page you can double-click with a screenshot of your React board for each resolved ticket (101, 102, 103). Append real runs to `output/audit_trail.json`. Finish `output/harness.md` so it covers tables, MCP tools, the five agents, API routes, the dashboard, and safety rules.

**Follow-up prompts:** several, because the first runs did not finish cleanly.

> pause for a sec / why is it taking so long / what do you think will keep it the most accurate to the instructions but still cut down the most time / why is it not working

**What was lacking after the first attempt:** the run completed and the cash math was right, but only one of three tickets reached a terminal state — and the stalls turned out to be gaps in the build rather than agent error. A human could approve a purchase order or a price override that **no tool could then carry out**, so those tickets could never close. The follow-ups were about diagnosing that honestly instead of re-running and hoping, and about weighing run time (~8s/model call, which doubled to ~22s mid-session on the provider's side) against staying faithful to "fill the Actual section from this run".

**Status:** done. One continuous run from reset: 101 resolved, 102 resolved, 103 blocked on cash — the shop is $104 short of the restock, which is the assignment's own no-negative-balance rule working rather than a failure. Opening $3,400 → closing $160, asserted against `cash_accounts` before the page would write. Six fixes came out of it: per-role request limits, `place_purchase_order`, `apply_price_override`, `cancel_approval`, a required `amount` on every approval, and the ticket↔invoice link surfaced as a fact rather than left as an inference.

---

## Problem 10: Reflection

**Prompt:**

> Problem 10: Reflection. Open `output/desk_tickets.html` and fill the Reflection tab. I'm going to give you my own thoughts on the answers and you help write in my vibe and make it detailed and thorough.
>
> **How would you evaluate the performance of the agents on each ticket and why?** — The first few times we attempted to do it, everything took way too long. We had to adjust multiple times. By the time we actually did a successful run it went much smoother, but it should never have taken so long to get through the first ticket. It's interesting that 103 was blocked because (elaborate on this).
>
> **For each ticket, how did Actual compare to the Expected plan you wrote earlier?** — You write this comparison.
>
> **What would have been simpler as one agent with tools, and why?** — I think some of the run time would maybe have been shorter. I think it was taking a while to make so many API calls, and maybe having just one agent handle everything rather than trying to communicate with others would have been a more efficient choice.
>
> **Describe three new problems Campus Customs might face that this agent team could solve with the tools you built.** — You write this.
>
> **Describe three new problems Campus Customs might face that this agent team could not solve with the tools you built, and explain the tools and agents you would need to solve them.** — You write this.
>
> Do you need more from me for this to be in my vibe? Tie every answer to this app and the three tickets you ran — use the ticket tabs and Cash tab on the same page as your evidence. Generic AI essays without Campus Customs details will score low, so be extra specific and use clear examples from what we actually did.

**Follow-up prompt:**

> I actually only needed 3 problems they might face that the agent team could not solve with the tools we built (explain the tools and agents we would need to solve them).

**What was lacking after the first version:** I answered the last question with five problems instead of the three asked for. Trimmed to three — money coming in, goods arriving against a frozen clock, and hearing back from a customer — each one mapping onto a specific ticket from this run, with the cash-forecasting gap folded into the first rather than dropped.

I also did one piece of analysis before writing that changed an answer. I tested whether any ordering of the three tickets could have funded all of them, and none can: the board asks for $3,504 against $3,400 of cash. So ticket 103 was blocked by arithmetic baked into the board, not by running last.

**Status:** done. All five questions answered on the Reflection tab, every claim tied to the ticket tabs and Cash tab on the same page — the `Inventory → Accounting` depth-2 hand-off on 101, Facilities and Customer Service at `0 steps` on 102, the $104 shortfall, `CC-MUG-CREST` sitting at qty 0, lease 1's `next_due` now at 2026-10-02, and the six unsent drafts. The Expected-vs-Actual comparison records where my plan was wrong, including that my most confident prediction about 103 failed partly because I changed the Accounting prompt between writing the plan and running it.

---

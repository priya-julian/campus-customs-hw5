# Campus Customs — Operations Desk

Design notes for the dashboard in `frontend/` (React + Vite + TypeScript).
It talks to the FastAPI backend at `http://localhost:8000`; the backend already
allows the Vite origin `http://localhost:5173`.

```bash
cd frontend && npm run dev
```

---

## The idea the whole thing hangs on

A person sitting here is not supervising software. They are **running a shop
with five employees who happen to be agents**, and their job is the one thing
the agents are forbidden to do: release money.

So the desk is laid out the way a real back office works — **work comes in on
the left, the team works in the middle, and the money lives on the right**,
where only the human can touch it. Nothing in the middle column can move a
cent. That is not just a layout convenience; it is the safety rule of the whole
assignment drawn as geography, and once you have sat with it for a minute you
stop needing to be told where the boundary is.

## Layout: three columns, each with one job

| Column | What it is | Why it sits there |
|---|---|---|
| **The Board** (left, 310px) | The three tickets | Work arrives here. Narrow, scannable, always visible — you never lose sight of what is outstanding while you are reading something else |
| **The Floor** (centre, fluid) | Agent lanes, the Boss's verdict, the live step stream | The widest column because it holds the most text and the most movement |
| **The Ledger** (right, 330px) | Checking balance, approval queue | The consequential column. Deliberately the one place a click changes the world |

A persistent top bar carries the four numbers you would want to glance at
without reading anything: **shop date, checking balance, how many approvals are
waiting on you**, and a reset button. The shop date is first on purpose — this
shop runs on `desk.date_today` (2026-08-31), not on your laptop's clock, and
putting that in the chrome stops anyone reasoning from the wrong calendar.

## How the agents read differently

Five agents could easily turn into five indistinguishable paragraphs. Three
things keep them apart:

**One colour axis, not five hues.** Every agent gets a blue, but a different
one — the Boss nearly navy (`#13306b`), Accounting indigo, Inventory a brighter
cerulean, Facilities a teal-leaning slate, Customer Service a soft periwinkle.
Choosing shades along one axis rather than five unrelated colours means the team
reads as *one team*, and it leaves the warm colours free to mean something.
They do: **gold is money waiting on you, green is money that moved**. Colour is
spent on consequence, not decoration.

**A monogram that never moves.** `BS`, `IN`, `AC`, `FA`, `CS`, always the same
square, always the same colour, in the lane, in the stream, and in the recap. You
learn the five tiles in about ten seconds and after that you can read the board
peripherally.

**Indentation that shows the chain of command.** A hand-off is not an aside — it
is the most interesting thing the team does. Events are indented by delegation
depth, so a specialist answering the Boss sits one step in, and a specialist who
was asked by *another specialist* sits two steps in. When Inventory discovers
that a vendor is frozen and goes straight to Accounting without routing back
through the Boss, you see that as a visibly deeper nesting, and the verdict
card labels it **"direct, not via Boss"**. That is the fully-connected team
doing the thing that makes it worth building, and it would be invisible in a
flat log.

### The five lanes — including the ones that do nothing

All five agents are always on screen, even when four of them never run. Idle
lanes fade to 62% opacity and show `0 steps, 0 tools`; the active one lifts,
takes a coloured cap, and shows a pulsing dot.

Showing the idle ones is a deliberate choice and my favourite detail here.
**A ticket that lights up all five lanes is a routing failure**, and this makes
that visible at a glance instead of buried in a transcript. On the rent ticket
you can see at once that Inventory and Customer Service stayed out of it — and
that is exactly right, because there is no SKU to look up and the landlord is
not a customer. Good routing is something you can *see* rather than audit.

### The tool chips

Every tool call appears as a small pill under the agent that made it, with the
`campus-customs_` prefix stripped so it reads as a verb: `check stock`,
`check vendor can ship`, `request approval`. They are colour-coded by
consequence rather than by name — **blue reads, gold writes, green touches
money** — so you can skim a run and see instantly that the agents did a lot of
looking and only one thing that changed the shop. Hovering a chip shows the
actual arguments.

## How resolved tickets show up

A ticket is not simply done-or-not, and pretending otherwise would be the
dishonest version of this screen. The backend's dispositions map to four badges
with deliberately plain words:

- **Open** — blue, nobody has worked it
- **Awaiting you** — gold, the team finished and a human now has a decision.
  This is the most common honest outcome and the wording points at the reader
- **Needs a person** — violet, the tools could not settle it
- **Resolved** — green, genuinely finished

A resolved ticket also gets a green left border and a soft green wash down the
card, so the board's state is legible from the corner of your eye without
reading a word. The left border is the carrier of status throughout — selection
turns it solid blue with a ring; resolution turns it green.

When a run ends, the **Boss's verdict card** drops in above the stream: the
disposition, the reasoning in the Boss's own words, one line per agent on what
they each contributed, the hand-off chain, and a gold **"Your move"** strip
naming the single next human action. The per-agent recap exists because the
stream is the truth but the recap is the *story*, and most of the time you want
the story.

## How cash shows up

The balance is the only element on the page rendered as a dark glass card with a
glow — it is the most important number here and it is allowed to look like it.
Underneath it:

- **A depletion meter.** Cash only leaves in this shop; no revenue is modelled.
  So the meter is a fuel gauge measured against the $3,400 opening balance, and
  it only ever shrinks. That is a more honest picture of this shop's
  predicament than a number alone, and it quietly explains why the spending
  order of rent versus an overdue invoice is a real decision.
- **A flash when it drops.** Approve a payment and the figure pulses amber for
  about a second as it falls. Money leaving should be felt, briefly. It is the
  one animation on the page that marks consequence rather than progress.
- **What is already queued.** `$2,400 requested` sits next to the balance, so
  you are never approving one payment in ignorance of the other one waiting
  behind it.

### The approval cards

Each pending request shows the amount big, the agent that prepared it, and
**the full rationale Accounting wrote** — the balance before and after, what it
unblocks, what will not fit afterwards. The prompt work that went into making
Accounting write a decidable rationale is wasted if the dashboard truncates it,
so the card scrolls rather than clips.

Two guards sit in the interface itself:

- **The approve button stays disabled until you type your name.** It is not
  decoration — that string lands in `payments.approved_by` and is the shop's
  evidence that a person, not a model, released the money. The field is labelled
  "Approving as" rather than "Name" to make that association.
- **Refusals are shown, not swallowed.** If a payment is approved but the
  account cannot cover it, the card says so in red with the tool's own words —
  *"checking holds 160.0 and rent is 2400.0"* — and the balance does not move.
  A dashboard that showed a cheerful "Approved!" over a refused payment would be
  lying about the state of the shop.

Decided requests collapse into a **Decided** list that distinguishes *Paid* from
*Approved, not paid* — because those are genuinely different states and the
second one means something went wrong.

## Small things that make it pleasant

- **Live, but not frantic.** While a run is going the stream polls every 1.2s
  and new cards slide in from below; a `live` dot pulses in the section header.
  Fast enough to feel alive, slow enough not to flicker.
- **The empty state has a voice.** The approvals column reads *"Nothing to
  approve. Agents can prepare payments — only you can release them."* It teaches
  the central rule at the moment you are most likely to wonder about it.
- **Typographic restraint.** One typeface, tabular numerals everywhere money
  appears so figures line up as they change, and a monospace face reserved for
  tool names and ticket numbers — the machine-ish things.
- **Toasts report outcomes, not actions.** "Paid. Checking is now $2,560.00",
  not "Success".
- **Reset is in the chrome, not the workspace.** Available, but not sitting
  where you might hit it while reading.

## What I would do next

Server-sent events instead of polling, so the stream is push rather than pull.
A visible delegation graph — the hand-off edges drawn between the lanes as they
happen, rather than implied by indentation. And a cash sparkline across the
whole session, since the depletion story is the most interesting thing about
this shop and right now you only see its current state.

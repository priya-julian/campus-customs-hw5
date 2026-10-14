"""Build output/resolved_board.html — the dashboard screenshots, one per ticket.

Images are embedded as base64 so the page is a single self-contained file that
opens on a double click with no server and no sibling folder to keep beside it.

    python backend/build_board_page.py 101=shot101.jpg 102=shot102.jpg 103=shot103.jpg
"""

from __future__ import annotations

import base64
import json
import mimetypes
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "resolved_board.html"
RESOLVED = ROOT / "output" / "resolved_tickets.json"

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Campus Customs — Resolved Board</title>
<style>
  :root {{
    --navy:#0a1a38; --navy-mid:#13306b; --blue:#1f5bb5; --blue-lt:#e6f0fc;
    --line:#d7e3f3; --ink:#0c1f3d; --ink-mid:#41587a; --ink-soft:#73879f;
    --green:#117054; --green-bg:#e3f5ee; --gold:#a8730a; --gold-bg:#fff6e2;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:0 0 60px; background:#f6fafe; color:var(--ink);
    font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
  header {{ background:linear-gradient(110deg,var(--navy),var(--navy-mid) 55%,var(--blue));
    color:#fff; padding:30px 34px 26px; }}
  header h1 {{ margin:0 0 6px; font-size:26px; letter-spacing:-.4px; }}
  header p {{ margin:0; opacity:.9; font-size:15px; }}
  .chips {{ margin-top:16px; display:flex; gap:8px; flex-wrap:wrap; }}
  .chip {{ background:rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.28);
    padding:4px 12px; border-radius:20px; font-size:13px; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:0 22px; }}
  section {{ margin-top:34px; background:#fff; border:1px solid var(--line);
    border-radius:14px; overflow:hidden; box-shadow:0 2px 10px rgba(12,31,61,.07); }}
  .head {{ padding:17px 22px; border-bottom:1px solid var(--line);
    display:flex; align-items:center; gap:13px; flex-wrap:wrap; background:#fbfdff; }}
  .head h2 {{ margin:0; font-size:19px; }}
  .num {{ font:700 13px/1 ui-monospace,Menlo,monospace; color:var(--blue); }}
  .badge {{ padding:3px 11px; border-radius:20px; font-size:12px; font-weight:700; }}
  .badge.resolved {{ background:var(--green-bg); color:var(--green); }}
  .badge.other {{ background:var(--gold-bg); color:var(--gold); }}
  .cash {{ margin-left:auto; font-size:14px; color:var(--ink-mid); font-variant-numeric:tabular-nums; }}
  .cash b {{ color:var(--ink); }}
  .shot {{ display:block; width:100%; border-bottom:1px solid var(--line); }}
  .body {{ padding:18px 22px 22px; }}
  .body p {{ margin:0 0 12px; color:var(--ink-mid); font-size:14.5px; }}
  h4 {{ margin:16px 0 7px; font-size:11px; letter-spacing:.11em; text-transform:uppercase;
    color:var(--ink-soft); }}
  ul {{ margin:0; padding-left:20px; font-size:14px; color:var(--ink-mid); }}
  li {{ margin-bottom:5px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:20px; }}
  footer {{ max-width:1180px; margin:34px auto 0; padding:18px 22px 0;
    border-top:1px solid var(--line); color:var(--ink-soft); font-size:13.5px; }}
  .none {{ color:var(--ink-soft); font-style:italic; font-size:14px; }}
</style>
</head>
<body>
<header>
  <div class="wrap" style="padding:0">
    <h1>Campus Customs — Resolved Board</h1>
    <p>The React dashboard after the full run, captured for each ticket.</p>
    <div class="chips">
      <span class="chip">Shop date {shop_date}</span>
      <span class="chip">Opening {opening}</span>
      <span class="chip">Closing {closing}</span>
      <span class="chip">{payments} payment(s) · {paid} out</span>
    </div>
  </div>
</header>
<main class="wrap">
{sections}
</main>
<footer>
  <p>Screenshots taken from the live dashboard on <code>http://localhost:5173</code>, backed by
  the FastAPI service on <code>:8000</code> over <code>data/campus_customs_new.db</code>.
  Figures match <code>cash_accounts</code> in that database.</p>
</footer>
</body>
</html>
"""

SECTION = """<section>
  <div class="head">
    <span class="num">#{tid}</span>
    <h2>{subject}</h2>
    <span class="badge {badge_cls}">{status_label}</span>
    <span class="cash">{cash_line}</span>
  </div>
  <img class="shot" src="data:{mime};base64,{b64}" alt="Dashboard showing ticket {tid}">
  <div class="body">
    <p>{outcome}</p>
    <div class="grid">
      <div>
        <h4>Agents on this ticket</h4>
        <ul>{agents}</ul>
      </div>
      <div>
        <h4>Human approvals</h4>
        {approvals}
      </div>
    </div>
  </div>
</section>
"""


def money(n: float) -> str:
    return f"${n:,.2f}"


def main(shots: dict[int, Path]) -> None:
    data = json.loads(RESOLVED.read_text())
    sections = []

    for ticket in data["tickets"]:
        tid = ticket["id"]
        path = shots[tid]
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        b64 = base64.b64encode(path.read_bytes()).decode()

        agents = "".join(
            f"<li><strong>{c['agent']}</strong> — {c['summary'] or 'routed and decided the ticket'}</li>"
            for c in ticket["agent_contributions"]
        ) or "<li class='none'>none recorded</li>"

        if ticket["human_approvals"]:
            approvals = "<ul>" + "".join(
                f"<li>#{a['approval_id']} {a['kind'].replace('_',' ')} "
                f"{money(a['amount']) if a['amount'] is not None else '—'} — "
                f"<strong>{a['decision']}</strong> by {a['decided_by']}"
                + (f", paid (balance {money(a['balance_after'])})" if a["money_moved"]
                   else ", no money moved")
                + "</li>"
                for a in ticket["human_approvals"]
            ) + "</ul>"
        else:
            approvals = "<p class='none'>No approval was needed — nothing on this ticket asked to spend.</p>"

        change = ticket["cash_change"]
        cash_line = (
            f"Cash <b>{money(ticket['balance_before'])}</b> → <b>{money(ticket['balance_after'])}</b>"
            + (f" ({money(change)} out)" if change else " (unchanged)")
        )
        resolved = ticket["final_status"] == "resolved"
        sections.append(SECTION.format(
            tid=tid, subject=ticket["subject"],
            badge_cls="resolved" if resolved else "other",
            status_label=ticket["final_status"].replace("_", " ").title(),
            cash_line=cash_line, mime=mime, b64=b64,
            outcome=ticket["outcome"], agents=agents, approvals=approvals,
        ))

    OUT.write_text(PAGE.format(
        shop_date=data["shop_date"],
        opening=money(data["opening_balance"]),
        closing=money(data["closing_balance"]),
        payments=data["payments_made"], paid=money(data["total_paid"]),
        sections="\n".join(sections),
    ))
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    mapping = {}
    for arg in sys.argv[1:]:
        key, _, value = arg.partition("=")
        mapping[int(key)] = Path(value)
    main(mapping)

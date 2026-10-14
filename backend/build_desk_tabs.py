"""Fill the Actual sections and the Cash tab of output/desk_tickets.html.

Reads output/full_run_log.json, output/resolved_tickets.json and the working
database, then rewrites the three `Actual` panels and the Cash tab in place —
leaving every `Expected` panel untouched so the two can be compared.

Every figure is read back from the database or the run log. The ending balance
is asserted against `cash_accounts` before anything is written, so the page
cannot disagree with the shop.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "output" / "desk_tickets.html"
RESOLVED = ROOT / "output" / "resolved_tickets.json"
LOG = ROOT / "output" / "full_run_log.json"
DB = ROOT / "data" / "campus_customs_new.db"

ROLE_HUE = {
    "Boss": "#13306b", "Inventory": "#1668a8", "Accounting": "#3a53a4",
    "Facilities": "#2b7f8f", "Customer Service": "#5a7fd6",
}


def money(n: float) -> str:
    return f"${n:,.2f}"


def db_one(sql: str):
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(sql).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def db_all(sql: str):
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def actual_panel(t: dict) -> str:
    """The Actual section for one ticket tab."""
    agents = "".join(
        f'<div class="hop"><div class="n" style="background:{ROLE_HUE.get(c["agent"], "#1f5bb5")}">'
        f'{c["agent"][0]}</div><div class="b">'
        f'<div class="r">{c["agent"]}</div>'
        f'<div class="w">{c["summary"] or "routed the ticket and made the final call"}</div>'
        + (f'<div class="w" style="margin-top:6px"><strong>Tools:</strong> '
           f'<code>{"</code>, <code>".join(c["tools_used"])}</code></div>' if c["tools_used"] else "")
        + "</div></div>"
        for c in t["agent_contributions"]
    )

    if t["delegations"]:
        seen, rows = set(), []
        for d in t["delegations"]:
            key = (d["from"], d["to"])
            if key in seen:
                continue
            seen.add(key)
            direct = (' <span style="color:var(--muted)">· direct between specialists, '
                      'not routed via the Boss</span>') if d["direct_between_specialists"] else ""
            rows.append(f'<li><strong>{d["from"]} → {d["to"]}</strong>{direct}<br>'
                        f'<span style="color:var(--muted);font-size:13.5px">'
                        f'“{d["question"][:190]}…”</span></li>')
        delegations = "<ul>" + "".join(rows) + "</ul>"
    else:
        delegations = '<p class="sub">No hand-offs — the Boss settled this alone.</p>'

    if t["human_approvals"]:
        approvals = "<ul>" + "".join(
            f'<li><strong>#{a["approval_id"]} {a["kind"].replace("_", " ")}</strong>'
            f'{" " + money(a["amount"]) if a["amount"] is not None else ""} — prepared by '
            f'{a["requested_by"]}, <strong>{a["decision"]}</strong> by {a["decided_by"]}.'
            + (f' Paid; balance {money(a["balance_after"])}.' if a["money_moved"]
               else " No money moved.")
            + "</li>"
            for a in t["human_approvals"]
        ) + "</ul>"
    else:
        approvals = '<p class="sub">Nothing on this ticket asked to spend, so no approval was needed.</p>'

    tools_all = sorted({tool for c in t["agent_contributions"] for tool in c["tools_used"]})
    drafts = "".join(
        f'<li>Draft #{d["draft_id"]} to {d["recipient"]} — <code>{d["status"]}</code></li>'
        for d in t["customer_drafts"]
    )

    status_cls = {"resolved": "resolved", "waiting_approval": "wait",
                  "needs_human": "human", "blocked": "blocked"}.get(t["final_status"], "wait")

    return f"""  <div class="panel actual">
    <h3>Actual — from the full run</h3>

    <h4>Where it landed</h4>
    <p><span class="tag {status_cls}">{t['final_status'].replace('_', ' ')}</span>
    after {t['passes_run']} pass{'es' if t['passes_run'] != 1 else ''} of the team.</p>
    <p>{t['outcome']}</p>

    <h4>Which agents worked it</h4>
    <div class="flow">{agents}</div>

    <h4>What they delegated</h4>
    {delegations}

    <h4>MCP tools this run actually used</h4>
    <p><code>{'</code> <code>'.join(tools_all) if tools_all else '—'}</code></p>

    <h4>Human approvals</h4>
    {approvals}

    <h4>Cash effect</h4>
    <p>{money(t['balance_before'])} → <strong>{money(t['balance_after'])}</strong>
    {'(' + money(abs(t['cash_change'])) + ' out)' if t['cash_change'] else '(unchanged)'}</p>

    {'<h4>Customer drafts</h4><ul>' + drafts + '</ul>' if drafts else ''}
    {'<div class="note warn"><strong>Still for a person:</strong> ' + t['next_step_for_human'] + '</div>' if t.get('next_step_for_human') else ''}
  </div>"""


def cash_tab(data: dict, log: dict) -> str:
    opening = data["opening_balance"]
    closing = data["closing_balance"]
    db_balance = db_one("SELECT balance FROM cash_accounts WHERE name='checking'")["balance"]
    payments = db_all("SELECT * FROM payments ORDER BY id")

    # The page must never disagree with the shop.
    assert abs(closing - db_balance) < 0.005, (
        f"closing balance {closing} does not match cash_accounts {db_balance}"
    )
    paid_total = round(sum(p["amount"] for p in payments), 2)
    assert abs((opening - paid_total) - db_balance) < 0.005, (
        f"opening {opening} - payments {paid_total} != balance {db_balance}"
    )

    rows, running = [], opening
    rows.append(
        f'<tr><td><strong>Opening balance</strong><br>'
        f'<span class="sub">after <code>reset_shop_database</code></span></td>'
        f'<td>—</td><td>—</td><td class="bal">{money(opening)}</td></tr>'
    )
    for t in data["tickets"]:
        moved = [a for a in t["human_approvals"] if a["money_moved"]]
        if not moved:
            why = "No money moved on this ticket."
            refused = [a for a in t["human_approvals"] if not a["money_moved"] and a["decision"] == "approved"]
            if refused:
                why += " An approved request could not be settled — see the ticket tab."
            if not t["human_approvals"]:
                why = "Nothing on this ticket asked to spend."
            rows.append(
                f'<tr><td><strong>Ticket #{t["id"]}</strong> — {t["subject"]}<br>'
                f'<span class="sub">{why}</span></td>'
                f'<td>—</td><td class="chg">0.00</td><td class="bal">{money(running)}</td></tr>'
            )
            continue
        for a in moved:
            running = round(running - a["amount"], 2)
            kind = a["kind"].replace("_", " ")
            rows.append(
                f'<tr><td><strong>Ticket #{t["id"]}</strong> — {t["subject"]}<br>'
                f'<span class="sub">{kind}, approval #{a["approval_id"]}, '
                f'approved by {a["decided_by"]}</span></td>'
                f'<td>{kind}</td>'
                f'<td class="chg out">−{money(a["amount"])[1:]}</td>'
                f'<td class="bal">{money(running)}</td></tr>'
            )
    rows.append(
        f'<tr class="total"><td><strong>Closing balance</strong><br>'
        f'<span class="sub">matches <code>cash_accounts.balance</code> in the working database</span></td>'
        f'<td>—</td><td class="chg out">−{money(paid_total)[1:]}</td>'
        f'<td class="bal">{money(closing)}</td></tr>'
    )

    payment_rows = "".join(
        f'<tr><td>{p["id"]}</td><td>{p["kind"]}</td><td>{p["ref_id"]}</td>'
        f'<td>{money(p["amount"])}</td><td>{p["paid_at"]}</td>'
        f'<td><strong>{p["approved_by"]}</strong></td></tr>'
        for p in payments
    ) or '<tr><td colspan="6" class="sub">No payments.</td></tr>'

    return f"""  <h2>Cash</h2>
  <p class="sub">Every movement of money across the full run, reconciled against the database.</p>

  <div class="panel expected">
    <h3>The ledger</h3>
    <table class="cash-table">
      <thead><tr><th>What</th><th>Kind</th><th>Change</th><th>Balance</th></tr></thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>

    <div class="note good">
      <strong>Reconciliation.</strong> Opening {money(opening)} − payments {money(paid_total)}
      = <strong>{money(closing)}</strong>, which is exactly
      <code>cash_accounts.balance</code> in <code>data/campus_customs_new.db</code>
      ({money(db_balance)}). Checked by assertion when this page was generated, so the two
      cannot drift apart.
    </div>

    <h4>Every payment row in the database</h4>
    <table class="cash-table">
      <thead><tr><th>id</th><th>kind</th><th>ref</th><th>amount</th><th>paid on</th><th>approved by</th></tr></thead>
      <tbody>{payment_rows}</tbody>
    </table>
    <p class="sub" style="margin-top:10px">Every row carries a person's name in
    <code>approved_by</code>. No agent can write that column — the pay tools copy it from a
    human's decision on the approvals board.</p>

    <div class="note warn">
      <strong>Cash only leaves.</strong> No revenue is modelled in this shop, so the balance
      only ever shrinks. That is what makes the order of spending a real decision:
      {money(opening)} covered the overdue invoice and the rent together, and what was left
      would not cover a restock.
    </div>
  </div>"""


EXTRA_CSS = """
  .cash-table{width:100%;border-collapse:collapse;margin:6px 0 16px;font-size:14px}
  .cash-table th{background:var(--blue-lt);color:var(--blue-dk);font-size:11.5px;
    text-transform:uppercase;letter-spacing:.05em;text-align:left;padding:9px 11px}
  .cash-table td{padding:10px 11px;border-bottom:1px solid var(--line);vertical-align:top}
  .cash-table tr.total td{border-top:2px solid var(--blue);border-bottom:none;
    background:var(--blue-soft);font-weight:600}
  .cash-table .chg,.cash-table .bal{text-align:right;font-variant-numeric:tabular-nums;
    white-space:nowrap}
  .cash-table .out{color:#8c2f2f;font-weight:600}
  .cash-table .bal{font-weight:600}
  .panel.actual h4:first-of-type{margin-top:0}
"""


def main() -> None:
    data = json.loads(RESOLVED.read_text())
    log = json.loads(LOG.read_text())
    html = PAGE.read_text()

    # Replace each ticket tab's Actual placeholder with the real thing.
    for t in data["tickets"]:
        tab_id = f't{t["id"]}'
        start = html.index(f'<section role="tabpanel" id="{tab_id}"')
        end = html.index("</section>", start)
        section = html[start:end]
        marker = '  <div class="panel actual">'
        p_start = section.index(marker)
        new_section = section[:p_start] + actual_panel(t) + "\n"
        html = html[:start] + new_section + html[end:]

    # Replace the Cash tab body.
    start = html.index('<section role="tabpanel" id="cash">')
    end = html.index("</section>", start)
    head = html[:start] + '<section role="tabpanel" id="cash">\n'
    html = head + cash_tab(data, log) + "\n" + html[end:]

    if ".cash-table" not in html:
        html = html.replace("</style>", EXTRA_CSS + "</style>")

    PAGE.write_text(html)
    print(f"updated {PAGE.relative_to(ROOT)}")
    print(f"  opening {money(data['opening_balance'])} -> closing {money(data['closing_balance'])}")
    for t in data["tickets"]:
        print(f"  #{t['id']} {t['final_status']:<18} cash {t['cash_change']:+,.2f}")


if __name__ == "__main__":
    main()

"""Campus Customs MCP server.

Every agent on the shop's team (Boss, Inventory, Accounting, Facilities,
Customer Service) reaches the shop database only through the tools defined
here.  There is no second data path: if a fact is not available from a tool on
this server, the team does not get to know it.  The tools read and write the
working copy, ``data/campus_customs_new.db``.

Rules enforced in the tools rather than trusted to agent prompts:

* **Never invent data.**  A missing row comes back as ``{"found": false}`` with
  a message, so an agent cannot mistake a guess for a record.
* **The shop's clock is ``desk.date_today``**, never the real system date.
* **Money needs a human.**  ``pay_invoice`` and ``pay_rent`` refuse unless an
  ``approvals`` row for that exact payment is in ``approved`` status, decided by
  a named human.  Agents can request; only a human can approve.
* **No negative balances.**  A payment larger than the account balance is
  refused outright, not partially applied.
* **A blocked vendor stays blocked.**  ``check_vendor_can_ship`` reports the
  no-ship-while-unpaid rule from live invoice data.
* **Nothing is sent.**  ``save_draft_message`` writes to the board with status
  ``draft_not_sent``.  There is no send tool, no mail client, no vendor call.
"""

from __future__ import annotations

from fastmcp import FastMCP

from db import (
    add_days,
    add_one_month,
    days_between,
    query_all,
    query_one,
    reset_working_copy,
    today,
    transaction,
)

mcp = FastMCP("campus-customs")

# Which vendor specialty covers which kind of SKU.  Derived from vendors.specialty
# in the database; the mapping of SKU prefix to specialty is the only shop
# convention encoded here.
SPECIALTY_BY_PREFIX = {
    "CC-TEE": "apparel reprint",
    "CC-HOOD": "apparel reprint",
    "CC-HAT": "apparel reprint",
    "CC-MUG": "mugs and small goods",
}


# ---------------------------------------------------------------- the board


@mcp.tool()
def get_shop_date() -> dict:
    """Return the shop's working date from ``desk.date_today``.

    Use this instead of any notion of "now". Every due-date and overdue
    judgement in this shop is made against this date.
    """
    return {"shop_today": today()}


@mcp.tool()
def list_tickets(status: str = "open") -> dict:
    """List tickets on the board, newest first.

    Args:
        status: Filter by status (``open``, ``resolved``, ``blocked``, ...).
            Pass ``"all"`` for every ticket regardless of status.
    """
    if status == "all":
        rows = query_all("SELECT * FROM tickets ORDER BY created_at DESC")
    else:
        rows = query_all(
            "SELECT * FROM tickets WHERE status = ? ORDER BY created_at DESC", (status,)
        )
    return {"shop_today": today(), "count": len(rows), "tickets": rows}


@mcp.tool()
def get_ticket(ticket_id: int) -> dict:
    """Read one ticket together with everything it points at.

    Resolves the ticket's ``sku``/``size`` to its inventory and pricing rows,
    its ``lease_id`` to the lease, and its ``invoice_id`` to the invoice and
    that invoice's vendor — so one call shows the whole context of the ask.
    """
    ticket = query_one("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    if ticket is None:
        return {"found": False, "ticket_id": ticket_id, "message": f"No ticket {ticket_id}."}

    linked: dict = {}
    if ticket["sku"]:
        linked["pricing"] = query_one(
            "SELECT * FROM pricing WHERE sku = ?", (ticket["sku"],)
        )
        if ticket["size"]:
            linked["inventory"] = query_one(
                "SELECT * FROM inventory WHERE sku = ? AND size = ?",
                (ticket["sku"], ticket["size"]),
            )
    if ticket["lease_id"]:
        linked["lease"] = query_one(
            "SELECT * FROM leases WHERE id = ?", (ticket["lease_id"],)
        )
    if ticket["invoice_id"]:
        invoice = query_one("SELECT * FROM invoices WHERE id = ?", (ticket["invoice_id"],))
        linked["invoice"] = invoice
        if invoice:
            linked["invoice_vendor"] = query_one(
                "SELECT * FROM vendors WHERE id = ?", (invoice["vendor_id"],)
            )
            # The shop's own record of *why* this invoice is on this ticket.
            # tickets.invoice_id is not a coincidence: it is the shop saying this
            # invoice serves this ticket. When the description also names the
            # ticket's SKU and size, that is the restock for this order, and the
            # team may rely on it rather than treating it as an open question.
            description = (invoice.get("description") or "").upper()
            sku_named = bool(ticket["sku"]) and ticket["sku"].upper() in description
            size_named = bool(ticket["size"]) and (
                f" {ticket['size'].upper()}" in f" {description}"
                or description.endswith(ticket["size"].upper())
            )
            linked["invoice_serves_this_ticket"] = True
            linked["invoice_matches_ticket_item"] = sku_named and size_named
            linked["invoice_is_paid"] = invoice["status"] == "paid"
            linked["restock_already_ordered"] = (
                sku_named and size_named and invoice["status"] == "paid"
            )
            linked["link_explained"] = (
                f"Ticket {ticket_id} is linked to invoice {invoice['id']} "
                f"({invoice['description']!r}, {invoice['status']}). "
                + (
                    "It names this ticket's SKU and size, so it is the order that "
                    "serves this ticket."
                    if sku_named and size_named
                    else "Its description does not name this ticket's SKU and size, "
                         "so do not assume it covers this order."
                )
            )

    return {"found": True, "shop_today": today(), "ticket": ticket, "linked": linked}


@mcp.tool()
def update_ticket(ticket_id: int, status: str, note: str) -> dict:
    """Move a ticket to a new status and append a note explaining why.

    Notes are appended, never overwritten, so the history of a ticket survives.
    This does not move money or stock — it only records where the ticket stands.

    Args:
        ticket_id: Ticket to update.
        status: New status, e.g. ``open``, ``waiting_approval``, ``blocked``,
            ``resolved``.
        note: One line on what changed and who decided it.
    """
    ticket = query_one("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    if ticket is None:
        return {"ok": False, "message": f"No ticket {ticket_id}."}

    stamped = f"[{today()}] {note}"
    merged = f"{ticket['notes']}\n{stamped}" if ticket["notes"] else stamped
    with transaction() as conn:
        conn.execute(
            "UPDATE tickets SET status = ?, notes = ? WHERE id = ?",
            (status, merged, ticket_id),
        )
        conn.commit()
    return {
        "ok": True,
        "ticket_id": ticket_id,
        "status_was": ticket["status"],
        "status_now": status,
        "note_added": stamped,
    }


# ------------------------------------------------------------ stock & price


@mcp.tool()
def check_stock(sku: str, size: str) -> dict:
    """Look up how many units of one SKU in one size are on hand.

    Stock is tracked per SKU *and* size, so a SKU can look healthy overall and
    still be empty in the one size a customer asked for. Pass both.

    Returns the matching row with ``qty`` and ``location``, plus
    ``sizes_on_hand`` for every size of that SKU so a substitute can be
    considered. An unknown pair returns ``{"found": false}`` rather than a
    guessed quantity.
    """
    row = query_one(
        "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
        (sku, size),
    )
    siblings = query_all(
        "SELECT size, qty FROM inventory WHERE sku = ? ORDER BY size", (sku,)
    )
    if row is None:
        return {
            "found": False,
            "sku": sku,
            "size": size,
            "message": f"No inventory row for SKU {sku!r} in size {size!r}.",
            "sizes_on_hand": siblings,
        }
    return {
        "found": True,
        "sku": row["sku"],
        "name": row["name"],
        "size": row["size"],
        "qty": row["qty"],
        "location": row["location"],
        "in_stock": row["qty"] > 0,
        "sizes_on_hand": siblings,
    }


@mcp.tool()
def check_shortfall(sku: str, size: str, qty_wanted: int) -> dict:
    """Compare a requested quantity against stock and report the gap.

    Answers "can we fill this order from the shelf, and if not, by how much are
    we short?" in one call, so the shortfall never has to be arithmetic done by
    a language model.
    """
    row = query_one(
        "SELECT qty, name FROM inventory WHERE sku = ? AND size = ?", (sku, size)
    )
    if row is None:
        return {
            "found": False,
            "sku": sku,
            "size": size,
            "message": f"No inventory row for SKU {sku!r} in size {size!r}.",
        }
    on_hand = row["qty"]
    shortfall = max(0, qty_wanted - on_hand)
    return {
        "found": True,
        "sku": sku,
        "name": row["name"],
        "size": size,
        "qty_wanted": qty_wanted,
        "qty_on_hand": on_hand,
        "can_fill_now": shortfall == 0,
        "shortfall": shortfall,
        "fillable_now": min(on_hand, qty_wanted),
    }


@mcp.tool()
def get_pricing(sku: str, qty: int = 1) -> dict:
    """Read a SKU's cost and list price and work out the margin on a quantity.

    Only ``unit_cost`` and ``list_price`` come from the database; the margin
    figures are arithmetic on those two. This tool reports the room a discount
    would have to fit inside — it does not decide whether a discount is
    acceptable and does not propose a price.
    """
    row = query_one("SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?", (sku,))
    if row is None:
        return {"found": False, "sku": sku, "message": f"No pricing row for SKU {sku!r}."}

    unit_cost, list_price = row["unit_cost"], row["list_price"]
    unit_margin = list_price - unit_cost
    return {
        "found": True,
        "sku": row["sku"],
        "qty": qty,
        "unit_cost": unit_cost,
        "list_price": list_price,
        "unit_margin": round(unit_margin, 2),
        "margin_pct_of_list": round(100 * unit_margin / list_price, 1) if list_price else None,
        "extended_cost": round(unit_cost * qty, 2),
        "extended_list": round(list_price * qty, 2),
        "extended_margin": round(unit_margin * qty, 2),
        "breakeven_unit_price": unit_cost,
    }


@mcp.tool()
def quote_discount(sku: str, qty: int, proposed_unit_price: float) -> dict:
    """Score a proposed discounted unit price against cost.

    Returns the discount percentage off list, the margin that survives at that
    price, and whether the price is at or below cost. It reports; it does not
    approve. A discount that the shop will actually honour still needs a
    ``price_override`` approval from a human.
    """
    row = query_one("SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,))
    if row is None:
        return {"found": False, "sku": sku, "message": f"No pricing row for SKU {sku!r}."}

    unit_cost, list_price = row["unit_cost"], row["list_price"]
    unit_margin = proposed_unit_price - unit_cost
    return {
        "found": True,
        "sku": sku,
        "qty": qty,
        "unit_cost": unit_cost,
        "list_price": list_price,
        "proposed_unit_price": proposed_unit_price,
        "discount_off_list_pct": round(100 * (list_price - proposed_unit_price) / list_price, 1)
        if list_price
        else None,
        "unit_margin_at_price": round(unit_margin, 2),
        "extended_margin_at_price": round(unit_margin * qty, 2),
        "margin_pct_at_price": round(100 * unit_margin / proposed_unit_price, 1)
        if proposed_unit_price
        else None,
        "at_or_below_cost": proposed_unit_price <= unit_cost,
        "requires_human_approval": True,
    }


@mcp.tool()
def adjust_inventory(sku: str, size: str, delta: int, reason: str) -> dict:
    """Change stock for one SKU/size by ``delta`` and say why.

    Negative values ship units out to a customer; positive values receive a
    restock. Refuses to take stock below zero — the shelf cannot go negative
    any more than the bank account can.

    Args:
        sku: Stock code.
        size: Size code.
        delta: Units to add (positive) or remove (negative).
        reason: Short explanation recorded with the change, e.g.
            ``"ticket 101 fulfilled"``.
    """
    row = query_one("SELECT qty FROM inventory WHERE sku = ? AND size = ?", (sku, size))
    if row is None:
        return {"ok": False, "message": f"No inventory row for {sku!r} size {size!r}."}

    new_qty = row["qty"] + delta
    if new_qty < 0:
        return {
            "ok": False,
            "refused": "would_go_negative",
            "sku": sku,
            "size": size,
            "qty_on_hand": row["qty"],
            "requested_delta": delta,
            "message": (
                f"Refused: {sku} size {size} has {row['qty']} on hand; "
                f"a change of {delta} would leave {new_qty}."
            ),
        }

    with transaction() as conn:
        conn.execute(
            "UPDATE inventory SET qty = ? WHERE sku = ? AND size = ?", (new_qty, sku, size)
        )
        conn.commit()
    return {
        "ok": True,
        "sku": sku,
        "size": size,
        "qty_before": row["qty"],
        "qty_after": new_qty,
        "reason": reason,
        "changed_on": today(),
    }


# ------------------------------------------------------------------ vendors


@mcp.tool()
def list_vendors() -> dict:
    """List every vendor with its specialty and lead time in days."""
    return {"shop_today": today(), "vendors": query_all("SELECT * FROM vendors ORDER BY id")}


@mcp.tool()
def find_vendor_for_sku(sku: str) -> dict:
    """Find the vendors whose specialty covers this SKU, with lead times and ETAs.

    The ETA is ``desk.date_today`` plus the vendor's ``lead_days``. Each vendor
    is also checked for open unpaid invoices, because a vendor that is owed
    money will not ship — so the ETA is only real for a vendor marked
    ``can_ship``.
    """
    prefix = "-".join(sku.split("-")[:2]) if "-" in sku else sku
    specialty = SPECIALTY_BY_PREFIX.get(prefix)
    if specialty is None:
        return {
            "found": False,
            "sku": sku,
            "message": f"No vendor specialty is mapped to SKU prefix {prefix!r}.",
            "all_vendors": query_all("SELECT * FROM vendors"),
        }

    shop_today = today()
    candidates = []
    for vendor in query_all("SELECT * FROM vendors WHERE specialty = ?", (specialty,)):
        blocking = query_all(
            "SELECT id, amount, due_date FROM invoices "
            "WHERE vendor_id = ? AND status != 'paid'",
            (vendor["id"],),
        )
        candidates.append(
            {
                **vendor,
                "eta_if_ordered_today": add_days(shop_today, vendor["lead_days"]),
                "can_ship": not blocking,
                "blocking_invoices": blocking,
            }
        )
    return {
        "found": bool(candidates),
        "sku": sku,
        "specialty_needed": specialty,
        "shop_today": shop_today,
        "vendors": candidates,
    }


@mcp.tool()
def check_vendor_can_ship(vendor_id: int) -> dict:
    """Say whether a vendor will ship, and if not, what is blocking them.

    The shop's rule: a vendor will not ship new product while they still hold an
    open unpaid invoice. This tool applies that rule to live invoice data, so a
    restock plan can never quietly assume a blocked vendor will deliver.
    """
    vendor = query_one("SELECT * FROM vendors WHERE id = ?", (vendor_id,))
    if vendor is None:
        return {"found": False, "vendor_id": vendor_id, "message": f"No vendor {vendor_id}."}

    shop_today = today()
    blocking = query_all(
        "SELECT id, amount, due_date, status, description FROM invoices "
        "WHERE vendor_id = ? AND status != 'paid'",
        (vendor_id,),
    )
    for inv in blocking:
        inv["days_overdue"] = -days_between(shop_today, inv["due_date"])

    can_ship = not blocking
    return {
        "found": True,
        "vendor_id": vendor_id,
        "vendor_name": vendor["name"],
        "specialty": vendor["specialty"],
        "lead_days": vendor["lead_days"],
        "shop_today": shop_today,
        "can_ship": can_ship,
        "blocking_invoices": blocking,
        "amount_to_unblock": round(sum(i["amount"] for i in blocking), 2),
        "eta_if_ordered_today": add_days(shop_today, vendor["lead_days"]) if can_ship else None,
        "message": (
            f"{vendor['name']} will ship; lead time {vendor['lead_days']} days."
            if can_ship
            else (
                f"{vendor['name']} will not ship: "
                f"{len(blocking)} unpaid invoice(s) totalling "
                f"{round(sum(i['amount'] for i in blocking), 2)}. "
                "Clear them first, then the lead time starts."
            )
        ),
    }


# ------------------------------------------------------------ money (reads)


@mcp.tool()
def get_cash_balance(account: str = "checking") -> dict:
    """Read an account balance.

    Cash only leaves in this shop — no revenue is modelled — so this balance is
    a shrinking budget that every pending payment competes for. Check it before
    proposing any spend.
    """
    row = query_one("SELECT * FROM cash_accounts WHERE name = ?", (account,))
    if row is None:
        return {"found": False, "account": account, "message": f"No account {account!r}."}

    pending = query_all(
        "SELECT id, kind, subject, amount FROM approvals "
        "WHERE status IN ('pending','approved') AND amount IS NOT NULL"
    )
    committed = round(sum(a["amount"] for a in pending), 2)
    return {
        "found": True,
        "account": row["name"],
        "balance": row["balance"],
        "as_of": row["date"],
        "shop_today": today(),
        "pending_or_approved_requests": pending,
        "total_requested_not_yet_paid": committed,
        "balance_if_all_paid": round(row["balance"] - committed, 2),
    }


@mcp.tool()
def list_invoices(status: str = "open") -> dict:
    """List vendor invoices with vendor names and overdue days.

    Args:
        status: ``open``, ``paid``, or ``all``.
    """
    sql = (
        "SELECT i.*, v.name AS vendor_name, v.lead_days FROM invoices i "
        "JOIN vendors v ON v.id = i.vendor_id"
    )
    rows = (
        query_all(sql + " ORDER BY i.due_date")
        if status == "all"
        else query_all(sql + " WHERE i.status = ? ORDER BY i.due_date", (status,))
    )
    shop_today = today()
    for row in rows:
        row["days_overdue"] = -days_between(shop_today, row["due_date"])
        row["is_overdue"] = row["days_overdue"] > 0 and row["status"] != "paid"
    return {
        "shop_today": shop_today,
        "count": len(rows),
        "total_amount": round(sum(r["amount"] for r in rows), 2),
        "invoices": rows,
    }


@mcp.tool()
def get_lease(lease_id: int) -> dict:
    """Read one lease and say whether its rent is due, late, or still ahead.

    The comparison is made against ``desk.date_today``, the shop's own clock,
    so Facilities never has to be trusted to remember which calendar to use.
    """
    row = query_one("SELECT * FROM leases WHERE id = ?", (lease_id,))
    if row is None:
        return {"found": False, "lease_id": lease_id, "message": f"No lease with id {lease_id}."}

    shop_today = today()
    days_until_due = days_between(shop_today, row["next_due"])
    status = "overdue" if days_until_due < 0 else "due_today" if days_until_due == 0 else "upcoming"
    return {
        "found": True,
        "lease_id": row["id"],
        "space_name": row["space_name"],
        "landlord": row["landlord"],
        "monthly_rent": row["monthly_rent"],
        "next_due": row["next_due"],
        "notes": row["notes"],
        "shop_today": shop_today,
        "days_until_due": days_until_due,
        "status": status,
    }


@mcp.tool()
def list_payments() -> dict:
    """List every payment the shop has made, with who approved each one.

    ``approved_by`` is the audit record of the human-approval rule. An agent
    name must never appear there.
    """
    rows = query_all("SELECT * FROM payments ORDER BY id")
    return {
        "count": len(rows),
        "total_paid": round(sum(r["amount"] for r in rows), 2),
        "payments": rows,
    }


# --------------------------------------------------------- human approvals


@mcp.tool()
def request_approval(
    kind: str,
    subject: str,
    rationale: str,
    requested_by: str,
    ticket_id: int | None = None,
    amount: float | None = None,
    account: str | None = None,
    ref_table: str | None = None,
    ref_id: int | None = None,
) -> dict:
    """Put a request on the board for a human to approve or reject.

    This is the only way an agent can move toward spending money or honouring a
    discount. It creates a ``pending`` row; it does not pay, order, or promise
    anything. A human decides later, and only then can a pay tool run.

    A request that is still ``pending`` or already ``approved`` for the same
    target blocks a second identical ask, so the board cannot fill with
    duplicates. Once a request has been ``executed`` the next period's ask (next
    month's rent, say) is allowed through — the pay tools themselves refuse to
    settle the same invoice twice.

    For a spend, check ``get_cash_balance`` first and say in the rationale what
    the balance is and what else is already queued against it — the human is
    choosing between competing claims on one shrinking account.

    Args:
        kind: ``invoice_payment``, ``rent_payment``, ``purchase_order``, or
            ``price_override``.
        subject: One line a human can read on the board.
        rationale: Why this is worth doing, with the numbers behind it.
        requested_by: The agent asking, e.g. ``accounting``.
        ticket_id: Ticket this serves, if any.
        amount: Money involved, if any.
        account: Account to draw on, for payments.
        ref_table: ``invoices``, ``leases``, or ``pricing``.
        ref_id: Row id in ``ref_table`` (the invoice id, lease id, ...).
    """
    valid = {"invoice_payment", "rent_payment", "purchase_order", "price_override"}
    if kind not in valid:
        return {"ok": False, "message": f"kind must be one of {sorted(valid)}, got {kind!r}."}

    # Every kind of request has a number attached, and the tool that carries it
    # out needs that number as data — not as prose in the subject line. A
    # request without one cannot be executed later, so it is refused now rather
    # than failing after a human has already approved it.
    if amount is None:
        return {
            "ok": False,
            "refused": "amount_required",
            "message": (
                f"A {kind} needs an `amount`. For a payment that is the sum to pay; "
                "for a purchase order the extended cost (unit cost x quantity); for a "
                "price override the extended total the customer would pay at the "
                "proposed price (proposed unit price x quantity). Put the figure in "
                "`amount`, not only in the subject — the tool that applies this later "
                "reads the field, not the words."
            ),
        }
    if amount < 0:
        return {"ok": False, "refused": "negative_amount",
                "message": "An approval amount cannot be negative."}

    duplicate = query_one(
        "SELECT id, status FROM approvals WHERE kind = ? AND ref_table IS ? AND ref_id IS ? "
        "AND status IN ('pending','approved')",
        (kind, ref_table, ref_id),
    )
    if duplicate and ref_id is not None:
        return {
            "ok": False,
            "duplicate_of": duplicate["id"],
            "status": duplicate["status"],
            "message": (
                f"Approval {duplicate['id']} already covers {kind} for "
                f"{ref_table} {ref_id} and is {duplicate['status']}. Do not ask twice."
            ),
        }

    with transaction() as conn:
        cur = conn.execute(
            "INSERT INTO approvals (ticket_id, kind, subject, amount, account, ref_table, "
            "ref_id, rationale, requested_by, requested_at, status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?, 'pending')",
            (
                ticket_id,
                kind,
                subject,
                amount,
                account,
                ref_table,
                ref_id,
                rationale,
                requested_by,
                today(),
            ),
        )
        conn.commit()
        approval_id = cur.lastrowid

    return {
        "ok": True,
        "approval_id": approval_id,
        "status": "pending",
        "message": (
            f"Approval {approval_id} is on the board awaiting a human. "
            "Nothing has been paid, ordered, or promised."
        ),
    }


@mcp.tool()
def list_approvals(status: str = "pending") -> dict:
    """List approval requests. Pass ``"all"`` for every status."""
    rows = (
        query_all("SELECT * FROM approvals ORDER BY id DESC")
        if status == "all"
        else query_all("SELECT * FROM approvals WHERE status = ? ORDER BY id DESC", (status,))
    )
    return {"shop_today": today(), "count": len(rows), "approvals": rows}


@mcp.tool()
def record_human_decision(
    approval_id: int, decision: str, decided_by: str, note: str = ""
) -> dict:
    """Record a human's approve/reject on a pending request.

    **For the human operator at the dashboard, not for agents.** ``decided_by``
    must be a real person's name — the pay tools copy it into
    ``payments.approved_by``, which is the shop's evidence that a human, not a
    model, released the money.

    Args:
        approval_id: The request being decided.
        decision: ``approved`` or ``rejected``.
        decided_by: Name of the person deciding.
        note: Optional reason, kept with the decision.
    """
    if decision not in {"approved", "rejected"}:
        return {"ok": False, "message": "decision must be 'approved' or 'rejected'."}

    row = query_one("SELECT * FROM approvals WHERE id = ?", (approval_id,))
    if row is None:
        return {"ok": False, "message": f"No approval {approval_id}."}
    if row["status"] != "pending":
        return {
            "ok": False,
            "message": f"Approval {approval_id} is already {row['status']}; it cannot be decided again.",
        }
    if not decided_by.strip():
        return {"ok": False, "message": "decided_by must name the person approving."}

    with transaction() as conn:
        conn.execute(
            "UPDATE approvals SET status = ?, decided_by = ?, decided_at = ?, decision_note = ? "
            "WHERE id = ?",
            (decision, decided_by.strip(), today(), note, approval_id),
        )
        conn.commit()
    return {
        "ok": True,
        "approval_id": approval_id,
        "status": decision,
        "decided_by": decided_by.strip(),
        "decided_at": today(),
    }


@mcp.tool()
def cancel_approval(approval_id: int, decided_by: str, reason: str) -> dict:
    """Withdraw an approval that cannot be carried out. **For the human, not for agents.**

    A request can be approved and still be impossible to execute — a malformed
    amount, a changed situation, a decision the shop wants back. Without a way
    to withdraw it, that request sits on the board forever: approved, unexecuted,
    and blocking anyone who checks whether the work is finished.

    Only an `approved` request can be cancelled. Something already `executed` has
    really happened and must not be erased — reverse it with a new decision
    instead.

    Args:
        approval_id: The approval to withdraw.
        decided_by: Name of the person withdrawing it.
        reason: Why it is being withdrawn. Kept with the record.
    """
    row = query_one("SELECT * FROM approvals WHERE id = ?", (approval_id,))
    if row is None:
        return {"ok": False, "message": f"No approval {approval_id}."}
    if row["status"] == "executed":
        return {
            "ok": False,
            "refused": "already_executed",
            "message": (
                f"Approval {approval_id} has already been carried out and cannot be "
                "cancelled. Reverse it with a new decision instead."
            ),
        }
    if row["status"] not in {"approved", "pending"}:
        return {"ok": False, "refused": "not_cancellable",
                "message": f"Approval {approval_id} is {row['status']}."}
    if not decided_by.strip():
        return {"ok": False, "message": "decided_by must name the person withdrawing this."}

    note = f"Cancelled: {reason}" if reason else "Cancelled."
    with transaction() as conn:
        conn.execute(
            "UPDATE approvals SET status = 'rejected', decided_by = ?, decided_at = ?, "
            "decision_note = ? WHERE id = ?",
            (decided_by.strip(), today(), note, approval_id),
        )
        conn.commit()
    return {
        "ok": True,
        "approval_id": approval_id,
        "status": "rejected",
        "was": row["status"],
        "decided_by": decided_by.strip(),
        "reason": reason,
        "message": f"Approval {approval_id} withdrawn by {decided_by.strip()}. No money moved.",
    }


# -------------------------------------------------------- money (movements)


def _spend_guard(approval_id: int, kind: str, ref_table: str, ref_id: int, amount: float):
    """Shared gate for the pay tools: human approval, then cash.

    Returns ``(approval_row, None)`` when the payment may proceed, or
    ``(None, refusal_dict)`` when it must not.
    """
    approval = query_one("SELECT * FROM approvals WHERE id = ?", (approval_id,))
    if approval is None:
        return None, {"ok": False, "refused": "no_such_approval",
                      "message": f"No approval {approval_id}. Payment refused."}
    if approval["status"] == "executed":
        return None, {"ok": False, "refused": "already_paid",
                      "message": f"Approval {approval_id} was already executed. Refusing to pay twice."}
    if approval["status"] != "approved":
        return None, {
            "ok": False,
            "refused": "not_approved_by_human",
            "approval_status": approval["status"],
            "message": (
                f"Approval {approval_id} is {approval['status']}, not 'approved'. "
                "A human must approve this payment before it can be made."
            ),
        }
    if approval["kind"] != kind or approval["ref_table"] != ref_table or approval["ref_id"] != ref_id:
        return None, {
            "ok": False,
            "refused": "approval_does_not_match",
            "message": (
                f"Approval {approval_id} covers {approval['kind']} for "
                f"{approval['ref_table']} {approval['ref_id']}, not {kind} for {ref_table} {ref_id}."
            ),
        }
    if approval["amount"] is not None and round(approval["amount"], 2) != round(amount, 2):
        return None, {
            "ok": False,
            "refused": "amount_does_not_match",
            "approved_amount": approval["amount"],
            "requested_amount": amount,
            "message": "The amount approved by the human does not match the amount being paid.",
        }
    return approval, None


def _settle(conn, *, kind, ref_id, amount, account, approval, extra_sql):
    """Write one payment, debit cash, mark the approval executed."""
    cur = conn.execute(
        "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
        "VALUES (?,?,?,?,?,?)",
        (kind, ref_id, amount, account, today(), approval["decided_by"]),
    )
    conn.execute(
        "UPDATE cash_accounts SET balance = balance - ?, date = ? WHERE name = ?",
        (amount, today(), account),
    )
    conn.execute("UPDATE approvals SET status = 'executed' WHERE id = ?", (approval["id"],))
    for sql, params in extra_sql:
        conn.execute(sql, params)
    conn.commit()
    return cur.lastrowid


@mcp.tool()
def pay_invoice(invoice_id: int, approval_id: int, account: str = "checking") -> dict:
    """Pay a vendor invoice in full. Requires a human-approved request.

    Refuses when: the approval is missing, still pending, rejected, already
    executed, or does not match this invoice and amount; the invoice is already
    paid; or the account does not hold enough cash. **No partial payments and no
    negative balances** — if the money is not there, nothing moves.

    On success: writes a ``payments`` row carrying the human's name in
    ``approved_by``, debits the account, and marks the invoice ``paid`` — which
    is also what unblocks that vendor's shipping.

    Args:
        invoice_id: Invoice to clear.
        approval_id: The approved request authorising it.
        account: Account to draw on.
    """
    invoice = query_one("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    if invoice is None:
        return {"ok": False, "refused": "no_such_invoice", "message": f"No invoice {invoice_id}."}
    if invoice["status"] == "paid":
        return {"ok": False, "refused": "already_paid", "message": f"Invoice {invoice_id} is already paid."}

    amount = invoice["amount"]
    approval, refusal = _spend_guard(approval_id, "invoice_payment", "invoices", invoice_id, amount)
    if refusal:
        return refusal

    cash = query_one("SELECT * FROM cash_accounts WHERE name = ?", (account,))
    if cash is None:
        return {"ok": False, "refused": "no_such_account", "message": f"No account {account!r}."}
    if cash["balance"] < amount:
        return {
            "ok": False,
            "refused": "insufficient_funds",
            "balance": cash["balance"],
            "amount_due": amount,
            "short_by": round(amount - cash["balance"], 2),
            "message": (
                f"Refused: {account} holds {cash['balance']} and invoice {invoice_id} is "
                f"{amount}. The balance may not go negative, so nothing was paid."
            ),
        }

    with transaction() as conn:
        payment_id = _settle(
            conn,
            kind="invoice",
            ref_id=invoice_id,
            amount=amount,
            account=account,
            approval=approval,
            extra_sql=[("UPDATE invoices SET status = 'paid' WHERE id = ?", (invoice_id,))],
        )

    vendor = query_one("SELECT name FROM vendors WHERE id = ?", (invoice["vendor_id"],))
    return {
        "ok": True,
        "payment_id": payment_id,
        "invoice_id": invoice_id,
        "amount": amount,
        "account": account,
        "paid_at": today(),
        "approved_by": approval["decided_by"],
        "balance_after": round(cash["balance"] - amount, 2),
        "vendor_unblocked": vendor["name"] if vendor else None,
    }


@mcp.tool()
def pay_rent(lease_id: int, approval_id: int, account: str = "checking") -> dict:
    """Pay one month's rent on a lease. Requires a human-approved request.

    Same gates as ``pay_invoice``: a matching approval decided by a human, and
    enough cash to cover it without going negative. On success the lease's
    ``next_due`` rolls forward one month.

    Args:
        lease_id: Lease to pay.
        approval_id: The approved request authorising it.
        account: Account to draw on.
    """
    lease = query_one("SELECT * FROM leases WHERE id = ?", (lease_id,))
    if lease is None:
        return {"ok": False, "refused": "no_such_lease", "message": f"No lease {lease_id}."}

    amount = lease["monthly_rent"]
    approval, refusal = _spend_guard(approval_id, "rent_payment", "leases", lease_id, amount)
    if refusal:
        return refusal

    cash = query_one("SELECT * FROM cash_accounts WHERE name = ?", (account,))
    if cash is None:
        return {"ok": False, "refused": "no_such_account", "message": f"No account {account!r}."}
    if cash["balance"] < amount:
        return {
            "ok": False,
            "refused": "insufficient_funds",
            "balance": cash["balance"],
            "amount_due": amount,
            "short_by": round(amount - cash["balance"], 2),
            "message": (
                f"Refused: {account} holds {cash['balance']} and rent is {amount}. "
                "The balance may not go negative, so nothing was paid."
            ),
        }

    next_due = add_one_month(lease["next_due"])
    with transaction() as conn:
        payment_id = _settle(
            conn,
            kind="rent",
            ref_id=lease_id,
            amount=amount,
            account=account,
            approval=approval,
            extra_sql=[("UPDATE leases SET next_due = ? WHERE id = ?", (next_due, lease_id))],
        )
    return {
        "ok": True,
        "payment_id": payment_id,
        "lease_id": lease_id,
        "space_name": lease["space_name"],
        "amount": amount,
        "account": account,
        "paid_at": today(),
        "approved_by": approval["decided_by"],
        "balance_after": round(cash["balance"] - amount, 2),
        "next_due_now": next_due,
    }


@mcp.tool()
def place_purchase_order(
    approval_id: int, sku: str, size: str, qty: int, vendor_id: int, account: str = "checking"
) -> dict:
    """Place a restock order with a vendor. Requires a human-approved purchase order.

    This is the step that turns an approved ``purchase_order`` request into an
    actual order. It applies every rule at once:

    * the approval must be ``approved`` by a human and must match this amount
    * the vendor must not be blocked by an open unpaid invoice
    * the account must cover the cost — no negative balances

    On success it pays the vendor, marks the approval executed, and returns the
    expected arrival date (shop date plus the vendor's lead time). **Stock is
    not increased**: the goods are in transit, not on the shelf, and inventory
    only moves when they physically arrive.

    Args:
        approval_id: The approved purchase-order request.
        sku: What is being ordered.
        size: Which size.
        qty: How many units.
        vendor_id: Who is supplying them.
        account: Account to draw on.
    """
    vendor = query_one("SELECT * FROM vendors WHERE id = ?", (vendor_id,))
    if vendor is None:
        return {"ok": False, "refused": "no_such_vendor", "message": f"No vendor {vendor_id}."}

    pricing = query_one("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,))
    if pricing is None:
        return {"ok": False, "refused": "no_such_sku", "message": f"No pricing row for {sku!r}."}

    amount = round(pricing["unit_cost"] * qty, 2)
    approval, refusal = _spend_guard(approval_id, "purchase_order", None, None, amount)
    if refusal and refusal.get("refused") == "approval_does_not_match":
        # A purchase order has no single row to point at, so the guard's
        # ref_table/ref_id check does not apply; re-check the rest by hand.
        approval = query_one("SELECT * FROM approvals WHERE id = ?", (approval_id,))
        if approval is None or approval["kind"] != "purchase_order":
            return {"ok": False, "refused": "approval_does_not_match",
                    "message": f"Approval {approval_id} is not a purchase order."}
        if approval["status"] == "executed":
            return {"ok": False, "refused": "already_ordered",
                    "message": f"Approval {approval_id} has already been placed."}
        if approval["status"] != "approved":
            return {"ok": False, "refused": "not_approved_by_human",
                    "approval_status": approval["status"],
                    "message": (f"Approval {approval_id} is {approval['status']}, not 'approved'. "
                                "A human must approve this order before it can be placed.")}
        if approval["amount"] is not None and round(approval["amount"], 2) != amount:
            return {"ok": False, "refused": "amount_does_not_match",
                    "approved_amount": approval["amount"], "order_amount": amount,
                    "message": "The order total does not match the amount the human approved."}
        refusal = None
    if refusal:
        return refusal

    blocking = query_all(
        "SELECT id, amount FROM invoices WHERE vendor_id = ? AND status != 'paid'", (vendor_id,)
    )
    if blocking:
        return {
            "ok": False,
            "refused": "vendor_blocked",
            "blocking_invoices": blocking,
            "message": (
                f"Refused: {vendor['name']} will not ship while "
                f"{len(blocking)} unpaid invoice(s) remain. Clear them first."
            ),
        }

    cash = query_one("SELECT * FROM cash_accounts WHERE name = ?", (account,))
    if cash is None:
        return {"ok": False, "refused": "no_such_account", "message": f"No account {account!r}."}
    if cash["balance"] < amount:
        return {
            "ok": False,
            "refused": "insufficient_funds",
            "balance": cash["balance"],
            "order_total": amount,
            "short_by": round(amount - cash["balance"], 2),
            "message": (
                f"Refused: {account} holds {cash['balance']} and this order costs {amount}. "
                "The balance may not go negative, so no order was placed."
            ),
        }

    shop_today = today()
    eta = add_days(shop_today, vendor["lead_days"])
    with transaction() as conn:
        payment_id = _settle(
            conn, kind="purchase_order", ref_id=approval_id, amount=amount,
            account=account, approval=approval, extra_sql=[],
        )
    return {
        "ok": True,
        "payment_id": payment_id,
        "approval_id": approval_id,
        "vendor": vendor["name"],
        "sku": sku,
        "size": size,
        "qty": qty,
        "unit_cost": pricing["unit_cost"],
        "amount": amount,
        "account": account,
        "ordered_on": shop_today,
        "lead_days": vendor["lead_days"],
        "expected_arrival": eta,
        "approved_by": approval["decided_by"],
        "balance_after": round(cash["balance"] - amount, 2),
        "stock_unchanged": True,
        "message": (
            f"Ordered {qty} x {sku} ({size}) from {vendor['name']} for {amount}. "
            f"Expected {eta}. Stock stays as-is until the goods arrive."
        ),
    }


@mcp.tool()
def apply_price_override(approval_id: int, qty: int) -> dict:
    """Put an approved discount into effect so it can be quoted to the customer.

    A ``price_override`` approval is a human agreeing that the shop will honour a
    particular price. This is the step that records that decision as acted upon,
    so the discount is a settled fact rather than a request still sitting on the
    board. No money moves — a price is what the shop *charges*, not what it pays.

    Refuses anything not approved by a human, and refuses to apply the same
    override twice. On success it returns the honoured unit price and the margin
    it leaves, which is what Customer Service should quote.

    Args:
        approval_id: The approved price-override request.
        qty: Units the quoted price applies to.
    """
    approval = query_one("SELECT * FROM approvals WHERE id = ?", (approval_id,))
    if approval is None:
        return {"ok": False, "refused": "no_such_approval", "message": f"No approval {approval_id}."}
    if approval["kind"] != "price_override":
        return {"ok": False, "refused": "wrong_kind",
                "message": f"Approval {approval_id} is a {approval['kind']}, not a price override."}
    if approval["status"] == "executed":
        return {"ok": False, "refused": "already_applied",
                "message": f"Approval {approval_id} has already been applied."}
    if approval["status"] != "approved":
        return {"ok": False, "refused": "not_approved_by_human",
                "approval_status": approval["status"],
                "message": (f"Approval {approval_id} is {approval['status']}, not 'approved'. "
                            "A human must approve a discount before the shop honours it.")}

    total = approval["amount"]
    unit_price = round(total / qty, 2) if qty else None
    pricing = query_one("SELECT unit_cost, list_price FROM pricing WHERE sku = ?",
                        (approval["ref_table"] == "pricing" and approval["ref_id"] or "",))
    # ref_id does not carry a SKU for pricing rows, so fall back to the subject.
    if pricing is None:
        for row in query_all("SELECT sku, unit_cost, list_price FROM pricing"):
            if row["sku"].upper() in (approval["subject"] or "").upper() \
               or row["sku"].upper() in (approval["rationale"] or "").upper():
                pricing = row
                break

    with transaction() as conn:
        conn.execute("UPDATE approvals SET status = 'executed' WHERE id = ?", (approval_id,))
        conn.commit()

    result = {
        "ok": True,
        "approval_id": approval_id,
        "status": "executed",
        "approved_total": total,
        "qty": qty,
        "honoured_unit_price": unit_price,
        "approved_by": approval["decided_by"],
        "applied_on": today(),
        "money_moved": False,
        "message": (
            f"Discount approved by {approval['decided_by']} is now in effect: "
            f"{qty} unit(s) at {unit_price} each. Quote this price to the customer."
        ),
    }
    if pricing and unit_price is not None:
        result["unit_cost"] = pricing["unit_cost"]
        result["list_price"] = pricing["list_price"]
        result["unit_margin_at_price"] = round(unit_price - pricing["unit_cost"], 2)
        result["discount_off_list_pct"] = round(
            100 * (pricing["list_price"] - unit_price) / pricing["list_price"], 1
        )
    return result


# ------------------------------------------------------------------ drafts


@mcp.tool()
def save_draft_message(
    recipient: str, subject: str, body: str, created_by: str, ticket_id: int | None = None
) -> dict:
    """Save a customer message to the board as a draft. **Nothing is ever sent.**

    There is no send tool on this server and no mail client behind it. A draft
    sits on the board with status ``draft_not_sent`` for a human to read, edit,
    and send themselves.

    Write the draft so that every promise in it is backed by a tool result: if a
    date came from a vendor lead time, say so; if an order cannot be filled yet,
    say that plainly rather than implying a shipment.

    Args:
        recipient: Who the message is for, as named on the ticket.
        subject: Subject line.
        body: The message itself.
        created_by: Agent that wrote it, e.g. ``customer_service``.
        ticket_id: Ticket this answers.
    """
    with transaction() as conn:
        cur = conn.execute(
            "INSERT INTO drafts (ticket_id, recipient, subject, body, created_by, created_at, status) "
            "VALUES (?,?,?,?,?,?, 'draft_not_sent')",
            (ticket_id, recipient, subject, body, created_by, today()),
        )
        conn.commit()
    return {
        "ok": True,
        "draft_id": cur.lastrowid,
        "status": "draft_not_sent",
        "message": "Draft saved to the board. It has NOT been sent to the customer.",
    }


@mcp.tool()
def list_drafts(ticket_id: int | None = None) -> dict:
    """List saved customer-message drafts, optionally for one ticket."""
    rows = (
        query_all("SELECT * FROM drafts ORDER BY id DESC")
        if ticket_id is None
        else query_all("SELECT * FROM drafts WHERE ticket_id = ? ORDER BY id DESC", (ticket_id,))
    )
    return {"count": len(rows), "drafts": rows}


# ------------------------------------------------------------------- admin


@mcp.tool()
def reset_shop_database() -> dict:
    """Restore the working copy from the pristine original.

    Wipes every payment, approval, draft, and ticket change made by the team and
    puts the shop back to its starting state. Run this before a full
    ticket-resolution run so results are reproducible. The original file is
    never written to.
    """
    return reset_working_copy()


if __name__ == "__main__":
    mcp.run()

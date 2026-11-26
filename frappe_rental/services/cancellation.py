"""Cancellation engine (T26, D5.7): policy tiers, fee and refund, preview, credit notes, refunds.

`compute()` is pure. `preview()` reads the booking and what was invoiced and paid, then calls it;
`cancel()` runs the same preview and settles exactly that, so the preview always equals the outcome.

Policy: tiers (hours before start, refund percent, flat fee). The tier with the largest threshold the
notice still meets applies; at exactly the threshold the tier applies. No tier met: nothing refunded.
  kept    = total x (100 - refund %) / 100 + fee, at most the total
  refund  = paid - kept (never below 0); the customer owes kept - paid when that is positive
A provider-side cancel refunds everything with no fee. No policy: full refund.

Settlement (posted invoices are never edited):
1. unpaid invoices are cancelled;
2. the paid part above `kept` is returned with a credit note (proportional across items and taxes);
3. when `kept` is more than what stays invoiced, a cancellation-fee invoice bills the difference;
4. the refund is paid by Payment Entry against the credit note.
Deposits are separate and settled through services.deposits.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime

from frappe_rental.compat import erpnext as compat
from frappe_rental.services import erpnext_sync


def compute(
	tiers: list[dict],
	hours_before: float,
	total: float,
	paid: float,
	by: str = "customer",
	precision: int = 2,
) -> dict:
	total, paid = flt(total, precision), flt(paid, precision)
	if by == "provider" or tiers is None:
		tier, pct, fee = None, 100.0, 0.0
	else:
		met = [t for t in tiers if flt(hours_before) >= flt(t["hours_before_start"])]
		tier = max(met, key=lambda t: flt(t["hours_before_start"])) if met else None
		pct = flt(tier["refund_percent"]) if tier else 0.0
		fee = flt(tier.get("fee")) if tier else 0.0
	kept = min(flt(total * (100 - pct) / 100 + fee, precision), total)
	return {
		"by": by,
		"hours_before": flt(hours_before, 2),
		"tier_hours": flt(tier["hours_before_start"]) if tier else None,
		"refund_percent": pct,
		"fee": fee,
		"total": total,
		"paid": paid,
		"kept": kept,
		"refund": flt(max(paid - kept, 0), precision),
		"amount_due": flt(max(kept - paid, 0), precision),
	}


def _invoices(booking) -> list:
	return frappe.get_all(
		"Sales Invoice",
		filters={"rental_booking": booking.name, "docstatus": 1, "is_return": 0},
		fields=["name", "grand_total", "rounded_total", "outstanding_amount"],
		order_by="posting_date desc, creation desc",
	)


def _credited(booking) -> float:
	return -flt(
		sum(
			flt(r)
			for r in frappe.get_all(
				"Sales Invoice",
				filters={"rental_booking": booking.name, "docstatus": 1, "is_return": 1},
				pluck="grand_total",
			)
		)
	)


def preview(booking, by: str = "customer", at=None) -> dict:
	if booking.docstatus != 1:
		frappe.throw(_("Only a confirmed booking has a cancellation outcome"))
	policy = frappe.db.get_value("Rental Type", booking.rental_type, "cancellation_policy")
	tiers = (
		frappe.get_all(
			"Rental Cancellation Tier",
			filters={"parent": policy, "parenttype": "Rental Cancellation Policy"},
			fields=["hours_before_start", "refund_percent", "fee"],
		)
		if policy
		else None
	)
	hours = (get_datetime(booking.from_datetime) - get_datetime(at or now_datetime())).total_seconds() / 3600
	invoices = _invoices(booking)
	paid = sum(
		flt(i.rounded_total or i.grand_total) - flt(i.outstanding_amount) for i in invoices
	) - _credited(booking)
	precision = frappe.get_precision("Rental Booking", "grand_total") or 2
	result = compute(tiers, hours, flt(booking.grand_total), max(paid, 0), by=by, precision=precision)
	result["policy"] = policy
	return result


def cancel(booking, by: str = "customer") -> dict:
	"""Cancel a confirmed booking under its policy. Returns the outcome (equal to `preview`)."""
	result = preview(booking, by=by)
	booking.flags.cancellation = result
	booking.cancel()
	return result


def settle(booking, result: dict) -> dict:
	"""on_cancel: post the outcome. Safe to run twice (it settles only what is still open)."""
	kept = flt(result["kept"])
	docs = {"credit_notes": [], "fee_invoice": None, "refund_entries": []}
	invoices = _invoices(booking)
	for inv in invoices:
		if flt(inv.outstanding_amount) == flt(inv.rounded_total or inv.grand_total):
			si = frappe.get_doc("Sales Invoice", inv.name)
			si.flags.ignore_permissions = True  # follows the permitted booking cancel
			si.cancel()
	invoices = _invoices(booking)
	invoiced = sum(flt(i.grand_total) for i in invoices) - _credited(booking)
	to_credit = flt(invoiced - kept, 2)
	for inv in invoices:
		if to_credit <= 0:
			break
		room = flt(inv.grand_total) + _credited_against(inv.name)
		amount = min(room, to_credit)
		if amount <= 0:
			continue
		docs["credit_notes"].append(_partial_credit(booking, inv.name, amount, flt(inv.grand_total)))
		to_credit = flt(to_credit - amount, 2)
	if kept > flt(invoiced, 2):
		docs["fee_invoice"] = _fee_invoice(booking, flt(kept - max(invoiced, 0), 2))
	remaining = flt(result["refund"])
	for note in docs["credit_notes"]:
		if remaining <= 0:
			break
		credit = -flt(frappe.db.get_value("Sales Invoice", note, "outstanding_amount"))
		amount = min(credit, remaining)
		if amount > 0:
			pe = compat.make_refund_entry(note, amount)
			pe.reference_no = booking.name
			pe.reference_date = pe.posting_date
			pe.flags.ignore_permissions = True  # refund decided by the cancellation policy
			pe.insert()
			pe.submit()
			docs["refund_entries"].append(pe.name)
			remaining = flt(remaining - amount, 2)
	_close_orders(booking)
	return docs


def _credited_against(si: str) -> float:
	return flt(
		sum(
			flt(r)
			for r in frappe.get_all(
				"Sales Invoice", filters={"return_against": si, "docstatus": 1}, pluck="grand_total"
			)
		)
	)


def _partial_credit(booking, si: str, amount: float, grand_total: float) -> str:
	note = compat.make_credit_note(si)
	factor = amount / grand_total if grand_total else 1
	for item in note.items:
		item.rate = flt(item.rate) * factor  # whole quantities: scale the price, not the qty
	note.rental_booking = booking.name
	note.remarks = _("Cancellation refund for {0}").format(booking.name)
	note.flags.ignore_permissions = True  # follows the permitted booking cancel
	note.flags.ignore_links = True  # the booking is already cancelled
	note.insert()
	note.submit()
	return note.name


def _fee_invoice(booking, amount: float) -> str:
	si = frappe.new_doc("Sales Invoice")
	si.update(
		{
			"customer": booking.customer,
			"company": booking.company,
			"currency": booking.currency,
			"rental_booking": booking.name,
			"ignore_pricing_rule": 1,
		}
	)
	row = {
		"item_code": erpnext_sync._charge_item(None),
		"description": _("Cancellation fee"),
		"qty": 1,
		"rate": amount,
	}
	account = erpnext_sync._income_account(booking)
	if account:
		row["income_account"] = account
	if booking.cost_center:
		row["cost_center"] = booking.cost_center
	si.append("items", row)
	si.flags.ignore_permissions = True  # fee set by the cancellation policy
	si.flags.ignore_links = True
	si.insert()
	si.submit()
	return si.name


def _close_orders(booking) -> None:
	for name in frappe.get_all(
		"Sales Order", filters={"rental_booking": booking.name, "docstatus": 1}, pluck="name"
	):
		so = frappe.get_doc("Sales Order", name)
		so.flags.ignore_permissions = True
		if frappe.db.exists("Sales Invoice", {"rental_booking": booking.name, "docstatus": 1}):
			so.update_status("Closed")
		else:
			so.cancel()

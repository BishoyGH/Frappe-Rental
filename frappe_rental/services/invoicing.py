"""Scheduled invoicing (T23, D6 rules 2 and 8).

A daily job turns due Rental Billing Schedule rows into Sales Invoices.

- Idempotency: each row is locked (`SELECT ... FOR UPDATE`) and re-read before it is billed, and the
  invoice stores the row in `rental_billing_row`. A rerun, or a second worker, finds the row Invoiced
  (or the existing invoice) and creates nothing.
- A one-off row that bills the whole booking reuses the T16 path (invoice made from the Sales Order).
  Every other row gets its own invoice: one item per booking line, split pro-rata by line amount.
- Negative rows (a shortening below what was billed) become credit notes against the last invoice.
- Email goes out through the `invoice_created` event (T31 Notification "Rental: invoice").
- `reschedule()` handles extension, shortening and early return on a confirmed booking: un-invoiced
  rows are rebuilt and over-billing is credited. Posted invoices are never edited.
Grouping: one invoice per booking. Per-customer consolidation is T50.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate, nowdate

from frappe_rental.compat import erpnext as compat
from frappe_rental.services import billable_events, billing, billing_schedule, erpnext_sync, events

ROW = "Rental Billing Schedule"


def run_due_invoices(today=None) -> list[str]:
	"""Scheduler (daily): invoice every Planned row due on or before `today`. Returns invoice names."""
	today = getdate(today or nowdate())
	rows = frappe.get_all(
		ROW,
		filters={"parenttype": "Rental Booking", "status": "Planned", "invoice_date": ["<=", today]},
		fields=["name", "parent"],
		order_by="invoice_date asc, idx asc",
	)
	made = []
	for row in rows:
		if frappe.db.get_value("Rental Booking", row.parent, "docstatus") != 1:
			continue
		try:
			name = invoice_row(row.name)
			frappe.db.commit()  # one row, one transaction: a later failure keeps earlier invoices
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=_("Rental invoicing failed for {0}").format(row.parent))
			continue
		if name:
			made.append(name)
	made += _bill_leftover_events(today)
	return made


def _bill_leftover_events(today) -> list[str]:
	"""Pending events on confirmed bookings with no planned row left get an invoice of their own."""
	bookings = frappe.get_all(
		"Rental Billable Event",
		filters={"status": "Pending", "event_date": ["<=", today]},
		pluck="rental_booking",
		distinct=True,
	)
	made = []
	for name in bookings:
		if frappe.db.get_value("Rental Booking", name, "docstatus") != 1:
			continue
		if frappe.db.exists(ROW, {"parent": name, "parenttype": "Rental Booking", "status": "Planned"}):
			continue
		try:
			si = invoice_events(frappe.get_doc("Rental Booking", name), today)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=_("Rental event invoicing failed for {0}").format(name))
			continue
		if si:
			made.append(si)
	return made


def invoice_events(booking, today=None) -> str | None:
	"""Bill the booking's due Pending events on one invoice. Returns it, or None if nothing was due."""
	names = billable_events.pending(booking.name, today)
	if not names:
		return None
	si = _new_invoice(booking, today or nowdate())
	billable_events.append_to_invoice(si, booking, names)
	for tax in compat.template_taxes(booking.taxes_and_charges):
		si.append("taxes", tax)
	si.flags.ignore_permissions = True  # events queued by permitted operations on a confirmed booking
	si.insert()
	billable_events.mark_invoiced(names, si.name)
	if _submit():
		si.submit()
		events.emit("invoice_created", si, extra={"rental_booking": booking.name})
	return si.name


def _new_invoice(booking, invoice_date):
	day = max(getdate(invoice_date), getdate(nowdate()))
	si = frappe.new_doc("Sales Invoice")
	si.update(
		{
			"customer": booking.customer,
			"company": booking.company,
			"currency": booking.currency,
			"posting_date": day,
			"set_posting_time": 1,
			"due_date": day,
			"rental_booking": booking.name,
			"ignore_pricing_rule": 1,
			"taxes_and_charges": booking.taxes_and_charges,
		}
	)
	if booking.cost_center and si.meta.has_field("cost_center"):
		si.cost_center = booking.cost_center
	return si


def invoice_row(row_name: str) -> str | None:
	"""Bill one schedule row. Safe to call twice; returns the invoice (existing or new)."""
	locked = frappe.db.sql(
		f"select name, parent, status, sales_invoice from `tab{ROW}` where name=%s for update",
		row_name,
		as_dict=True,
	)
	if not locked:
		return None
	if locked[0].status != "Planned":
		return locked[0].sales_invoice
	existing = frappe.db.get_value("Sales Invoice", {"rental_billing_row": row_name, "docstatus": ["<", 2]})
	booking = frappe.get_doc("Rental Booking", locked[0].parent)
	row = next(r for r in booking.billing_schedule if r.name == row_name)
	if existing:
		name = existing
	elif flt(row.amount) < 0:
		name = _credit_note(booking, row)
	elif _is_whole_booking(booking, row):
		name = erpnext_sync.make_sales_invoice(booking, submit=_submit())
		frappe.db.set_value("Sales Invoice", name, "rental_billing_row", row_name)
	else:
		name = _period_invoice(booking, row)
	status = "Credited" if flt(row.amount) < 0 else "Invoiced"
	frappe.db.set_value(ROW, row_name, {"status": status, "sales_invoice": name})
	return name


def _submit() -> bool:
	value = frappe.db.get_single_value("Rental Settings", "submit_scheduled_invoices")
	return value is None or bool(value)


def _is_whole_booking(booking, row) -> bool:
	return len(booking.billing_schedule) == 1 and flt(row.amount) == flt(booking.net_total)


def _period_invoice(booking, row) -> str:
	si = _new_invoice(booking, row.invoice_date)
	si.rental_billing_row = row.name
	account = erpnext_sync._income_account(booking)
	lines = erpnext_sync._item_rows(booking)
	precision = billing._precision(booking)
	amounts = billing_schedule._split([flt(r["rate"]) for r in lines], flt(row.amount), precision)
	period = _("{0} to {1}").format(row.period_from, row.period_to)
	for line, amount in zip(lines, amounts, strict=True):
		if not amount:
			continue
		item = {**line, "rate": amount, "description": f"{line['description']}, {period}"}
		if account and line.get("rental_booking_line"):
			item["income_account"] = account
		if booking.cost_center:
			item["cost_center"] = booking.cost_center
		item.update(_deferred(booking, row))
		si.append("items", item)
	extras = billable_events.append_to_invoice(
		si, booking, billable_events.pending(booking.name, row.invoice_date)
	)
	for tax in compat.template_taxes(booking.taxes_and_charges):
		si.append("taxes", tax)
	si.flags.ignore_permissions = True  # system job billing a confirmed booking on its schedule
	si.insert()
	billable_events.mark_invoiced(extras, si.name)
	if _submit():
		si.submit()
		events.emit("invoice_created", si, key=str(row.period_from), extra={"rental_booking": booking.name})
	return si.name


def _deferred(booking, row) -> dict:
	"""D5.4: advance-billed periods recognise income over the service dates when the type enables it."""
	if not frappe.db.get_value("Rental Type", booking.rental_type, "enable_deferred_revenue"):
		return {}
	account = frappe.get_cached_value("Company", booking.company, "default_deferred_revenue_account")
	if not account:
		return {}
	return {
		"enable_deferred_revenue": 1,
		"deferred_revenue_account": account,
		"service_start_date": row.period_from,
		"service_end_date": row.period_to,
	}


def _credit_note(booking, row) -> str:
	against = frappe.get_all(
		"Sales Invoice",
		filters={"rental_booking": booking.name, "docstatus": 1, "is_return": 0},
		order_by="posting_date desc, creation desc",
		pluck="name",
		limit=1,
	)
	if not against:
		frappe.throw(_("Nothing invoiced on {0} to credit").format(booking.name))
	note = compat.make_credit_note(against[0])
	note.rental_booking = booking.name
	note.rental_billing_row = row.name
	keep = note.items[0]
	keep.qty = -1
	keep.rate = abs(flt(row.amount))
	keep.description = row.adjustment_note or _("Credit for {0}").format(booking.name)
	note.set("items", [keep])
	note.flags.ignore_permissions = True  # credit raised by a permitted booking change
	note.insert()
	note.submit()
	return note.name


def on_confirm(booking) -> None:
	"""Booking submitted: date "At confirmation" rows today, then bill what is due if Settings auto-invoice."""
	today = getdate(nowdate())
	plan = billing.resolve_plan(booking)
	for r in booking.billing_schedule:
		if (
			r.status == "Planned"
			and r.idx == 1
			and (plan.get("timing") == "At confirmation" or plan.get("first_invoice") == "At confirmation")
		):
			frappe.db.set_value(ROW, r.name, "invoice_date", min(getdate(r.invoice_date), today))
	if not frappe.db.get_single_value("Rental Settings", "auto_invoice"):
		return
	due = frappe.get_all(
		ROW,
		filters={
			"parent": booking.name,
			"parenttype": "Rental Booking",
			"status": "Planned",
			"invoice_date": ["<=", today],
		},
		pluck="name",
		order_by="idx asc",
	)
	for name in due:
		invoice_row(name)
	if not due and not booking.billing_schedule:
		erpnext_sync.make_sales_invoice(booking)


def reschedule(booking, to_datetime=None, net_total=None) -> list[dict]:
	"""Extension, shortening or early return on a confirmed booking.

	Rebuilds un-invoiced rows for the new end and total, keeps invoiced rows, and credits at once
	when more was invoiced than the new total. Returns the new rows.
	"""
	if booking.docstatus != 1:
		frappe.throw(_("Reschedule applies to confirmed bookings; edit the draft instead"))
	if to_datetime:
		booking.db_set("to_datetime", get_datetime(to_datetime), update_modified=False)
	if net_total is not None:
		booking.db_set("net_total", flt(net_total), update_modified=False)
	planned = [r.name for r in booking.billing_schedule if r.status == "Planned"]
	billing.update_schedule(booking, force=True)
	for name in planned:
		frappe.db.delete(ROW, name)
	for idx, r in enumerate(booking.billing_schedule, 1):
		r.idx = idx
		if r.status == "Planned":
			r.parent, r.parenttype, r.parentfield = booking.name, "Rental Booking", "billing_schedule"
			r.name = frappe.generate_hash(length=10)
			r.db_insert()
		else:
			r.db_update()
	new = [r for r in booking.billing_schedule if r.status == "Planned"]
	for r in new:
		if flt(r.amount) < 0:
			invoice_row(r.name)
	return [r.as_dict() for r in new]

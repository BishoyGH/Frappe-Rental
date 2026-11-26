"""Billable events (T24, D6): extra charges that join the booking's next invoice.

Late fees (T27), damage (T28), delivery, extensions and termination fees are queued as Rental
Billable Event rows. The invoicing job adds every Pending event to the next period invoice of the
booking; when the booking has no planned row left, the job bills them on their own invoice. Each
event is billed once: it is locked, then marked Invoiced with the invoice link in the same transaction.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

DOCTYPE = "Rental Billable Event"
ACCOUNT_SETTING = {
	"Late fee": "late_fee_income_account",
	"Damage": "damage_recovery_account",
	"Termination fee": "rental_income_account",
	"Delivery": "rental_income_account",
	"Extension": "rental_income_account",
	"Other": "rental_income_account",
}


def validate(doc) -> None:
	if flt(doc.amount) <= 0:
		frappe.throw(_("Amount must be more than zero"))
	if doc.status == "Invoiced" and not doc.sales_invoice:
		frappe.throw(_("An invoiced event needs its Sales Invoice"))
	if not doc.rental_booking and not doc.rental_contract:
		frappe.throw(_("A billable event needs a booking or a contract"))
	if not doc.rental_booking:
		doc.customer = doc.customer or frappe.db.get_value("Rental Contract", doc.rental_contract, "customer")
		doc.currency = doc.currency or frappe.db.get_value("Rental Contract", doc.rental_contract, "currency")
	if (
		doc.is_new()
		and doc.rental_booking
		and frappe.db.get_value("Rental Booking", doc.rental_booking, "docstatus") == 2
	):
		frappe.throw(_("Booking {0} is cancelled").format(doc.rental_booking))


def add(
	booking: str | None,
	event_type: str,
	amount,
	description=None,
	source=None,
	event_date=None,
	contract=None,
) -> str:
	"""Queue a charge. With `source` (a document), the same source never queues twice."""
	if source is not None:
		existing = frappe.db.get_value(
			DOCTYPE,
			{"source_doctype": source.doctype, "source_name": source.name, "event_type": event_type},
		)
		if existing:
			return existing
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"rental_booking": booking,
			"rental_contract": contract,
			"event_type": event_type,
			"amount": flt(amount),
			"description": description or _(event_type),
			"event_date": event_date or nowdate(),
			"source_doctype": source.doctype if source is not None else None,
			"source_name": source.name if source is not None else None,
		}
	)
	doc.flags.ignore_permissions = True  # queued by a permitted operation (return, damage, change)
	doc.insert()
	return doc.name


def pending(booking: str, upto=None) -> list[str]:
	"""Pending events of `booking`, locked for this transaction."""
	upto = getdate(upto or nowdate())
	return [
		r[0]
		for r in frappe.db.sql(
			f"select name from `tab{DOCTYPE}` where rental_booking=%s and status='Pending'"
			" and event_date<=%s order by event_date, creation for update",
			(booking, upto),
		)
	]


def income_account(event, company: str) -> str | None:
	account = event.income_account or frappe.db.get_single_value(
		"Rental Settings", ACCOUNT_SETTING.get(event.event_type, "rental_income_account")
	)
	if account and frappe.db.get_value("Account", account, "company") == company:
		return account
	return None


def append_to_invoice(si, booking, names: list[str]) -> list[str]:
	"""Add events as invoice items. Returns the names added; mark them with `mark_invoiced` after insert."""
	added = []
	for name in names:
		event = frappe.get_doc(DOCTYPE, name)
		row = {
			"item_code": _event_item(event.event_type),
			"description": event.description or event.event_type,
			"qty": 1,
			"rate": flt(event.amount),
		}
		account = income_account(event, booking.company)
		if account:
			row["income_account"] = account
		if booking.cost_center:
			row["cost_center"] = booking.cost_center
		si.append("items", row)
		added.append(name)
	return added


def mark_invoiced(names: list[str], sales_invoice: str) -> None:
	for name in names:
		frappe.db.set_value(DOCTYPE, name, {"status": "Invoiced", "sales_invoice": sales_invoice})


def _event_item(event_type: str) -> str:
	"""A non-stock service Item per event type, created the first time ("Rental Late fee")."""
	code = f"Rental {event_type}"
	if frappe.db.exists("Item", code):
		return code
	from frappe_rental.services.rental_item import _item_group, _stock_uom

	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": code,
			"item_group": _item_group(),
			"stock_uom": _stock_uom(),
			"is_stock_item": 0,
			"is_sales_item": 1,
		}
	).insert(ignore_permissions=True)  # system-made service item for an event type
	return code

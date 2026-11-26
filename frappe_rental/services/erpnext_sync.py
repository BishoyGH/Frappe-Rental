"""ERPNext sync (T16): a confirmed booking gets a Sales Order; a one-off Sales Invoice follows.

- Each booking line becomes one Sales Order Item (qty 1, rate = the line amount) so totals match the
  booking to the cent whatever the quantity; the line's qty and period go in the description.
- Each charge becomes an item too: the Rental Charge's Item, or a service Item created for it.
- Taxes come from the booking's template, so ERPNext's totals equal the booking's.
- Every step looks for its existing document first, so running it twice creates nothing new.
- Cancelling the booking cancels an unpaid invoice (or issues a credit note for a paid one), then the
  Sales Order.
ERPNext calls that differ between versions go through `compat.erpnext`.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from frappe_rental.compat import erpnext as compat
from frappe_rental.services import events
from frappe_rental.services.rental_item import _item_group, _stock_uom, income_account


def _existing(doctype: str, booking: str) -> str | None:
	return frappe.db.get_value(doctype, {"rental_booking": booking, "docstatus": ["<", 2]}, "name")


def make_sales_order(booking) -> str:
	"""Create and submit the Sales Order for a confirmed booking. Returns its name."""
	name = _existing("Sales Order", booking.name)
	if not name:
		so = frappe.new_doc("Sales Order")
		delivery = max(getdate(booking.from_datetime), getdate(nowdate()))
		so.update(
			{
				"customer": booking.customer,
				"company": booking.company,
				"currency": booking.currency,
				"transaction_date": nowdate(),
				"delivery_date": delivery,
				"order_type": "Sales",
				"rental_booking": booking.name,
				"ignore_pricing_rule": 1,
				"taxes_and_charges": booking.taxes_and_charges,
			}
		)
		if booking.price_list:
			so.selling_price_list = booking.price_list
		if booking.cost_center and so.meta.has_field("cost_center"):
			so.cost_center = booking.cost_center
		for row in _item_rows(booking):
			so.append("items", {**row, "delivery_date": delivery})
		for tax in compat.template_taxes(booking.taxes_and_charges):
			so.append("taxes", tax)
		# The booking's submit permission was checked; the order is its system-made mirror.
		so.flags.ignore_permissions = True
		so.insert()
		so.submit()
		name = so.name
	if booking.sales_order != name:
		booking.db_set("sales_order", name, update_modified=False)
	return name


def make_sales_invoice(booking, submit: bool = True) -> str:
	"""Create the one-off Sales Invoice from the booking's Sales Order. Returns its name."""
	if booking.docstatus != 1:
		frappe.throw(_("Confirm the booking before invoicing it"))
	name = _existing("Sales Invoice", booking.name)
	if not name:
		si = compat.make_sales_invoice_from_order(make_sales_order(booking))
		si.rental_booking = booking.name
		account = _income_account(booking)
		for item in si.items:
			if account and item.rental_booking_line:
				item.income_account = account
			if booking.cost_center:
				item.cost_center = booking.cost_center
		si.flags.ignore_permissions = True  # same as the Sales Order: a mirror of a permitted booking
		si.insert()
		if submit:
			si.submit()
			events.emit("invoice_created", si, extra={"rental_booking": booking.name})
		name = si.name
	if booking.sales_invoice != name:
		booking.db_set("sales_invoice", name, update_modified=False)
	return name


def reverse(booking) -> None:
	"""Undo the ERPNext side of a cancelled booking. Safe to run twice."""
	for name in frappe.get_all(
		"Sales Invoice",
		filters={"rental_booking": booking.name, "docstatus": 1, "is_return": 0},
		pluck="name",
	):
		si = frappe.get_doc("Sales Invoice", name)
		si.flags.ignore_permissions = True  # reversal follows the permitted booking cancel
		if flt(si.outstanding_amount) == flt(si.rounded_total or si.grand_total):
			si.cancel()
		elif not frappe.db.exists("Sales Invoice", {"return_against": name, "docstatus": 1}):
			note = compat.make_credit_note(name)
			note.rental_booking = booking.name
			note.flags.ignore_permissions = True
			note.flags.ignore_links = True  # the booking is already cancelled when its note is made
			note.insert()
			note.submit()
	for name in frappe.get_all(
		"Sales Order", filters={"rental_booking": booking.name, "docstatus": 1}, pluck="name"
	):
		so = frappe.get_doc("Sales Order", name)
		if frappe.db.exists(
			"Sales Invoice", {"rental_booking": booking.name, "docstatus": 1, "is_return": 0}
		):
			so.flags.ignore_permissions = True
			so.update_status("Closed")  # invoiced and credited: close instead of cancel
			continue
		so.flags.ignore_permissions = True
		so.cancel()


def _item_rows(booking) -> list[dict]:
	rows = []
	for line in booking.lines:
		item_code = frappe.db.get_value("Rental Item", line.rental_item, "item_code")
		if not item_code:
			frappe.throw(_("Row {0}: {1} has no ERPNext Item").format(line.idx, line.rental_item))
		period = f"{flt(line.qty):g} x {flt(line.units):g} {line.time_unit or ''}".strip()
		rows.append(
			{
				"item_code": item_code,
				"description": f"{line.rental_item} {line.rental_unit or ''} ({period})",
				"qty": 1,
				"rate": flt(line.amount),
				"rental_unit": line.rental_unit,
				"rental_booking_line": line.name,
			}
		)
	for charge in booking.charges:
		if not flt(charge.amount):
			continue
		rows.append(
			{
				"item_code": _charge_item(charge.charge),
				"description": charge.description or charge.charge,
				"qty": 1,
				"rate": flt(charge.amount),
			}
		)
	return rows


def _charge_item(charge: str | None) -> str:
	"""The Item for a Rental Charge, creating a non-stock service Item the first time."""
	if charge:
		item = frappe.db.get_value("Rental Charge", charge, "item")
		if item:
			return item
	code = charge or _("Rental Charge")
	if not frappe.db.exists("Item", code):
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
		).insert(ignore_permissions=True)  # system-made service item for a charge
	if charge:
		frappe.db.set_value("Rental Charge", charge, "item", code)
	return code


def _income_account(booking) -> str | None:
	account = income_account(booking.rental_type)
	if account and frappe.db.get_value("Account", account, "company") == booking.company:
		return account
	return None

"""My bookings portal (T37): what a signed-in customer sees and may do with their own bookings.

Customers have no desk permissions on any rental doctype. Every call resolves the booking through
``checkout.own_booking`` (the booking's customer must be one the user acts for; anything else looks like
"not found") and then reads or acts as Administrator inside ``checkout._as_system``. Nothing here accepts
a document name for anything but the booking, and invoices and contracts are only reachable through
that booking's own links.

Change: a held or draft booking can move to new dates (re-priced, re-checked for availability). A
confirmed booking cannot be edited by the customer; it can be cancelled under its policy, with the
refund shown first, and booked again.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from frappe_rental.services import booking as booking_service
from frappe_rental.services import cancellation, checkout, lifecycle, timeline


def listing(start: int = 0, page_length: int = 20) -> dict:
	customers = checkout.my_customers()
	if not customers:
		return {"rows": [], "total": 0}
	filters = {"customer": ["in", customers], "docstatus": ["<", 2]}
	with checkout._as_system():  # row filter above is the permission check
		rows = frappe.get_all(
			"Rental Booking",
			filters=filters,
			fields=["name", "status", "docstatus", "from_datetime", "to_datetime", "currency", "grand_total"],
			order_by="from_datetime desc",
			start=cint(start),
			page_length=max(1, min(cint(page_length) or 20, 100)),
		)
		for row in rows:
			item = frappe.db.get_value("Rental Booking Line", {"parent": row.name}, "rental_item")
			row["item_name"] = item and frappe.db.get_value("Rental Item", item, "item_name")
		total = frappe.db.count("Rental Booking", filters)
	return {"rows": rows, "total": total}


def booking_invoices(doc) -> list[dict]:
	"""Submitted invoices that carry this booking, directly or as a consolidated line."""
	direct = frappe.get_all(
		"Sales Invoice", filters={"rental_booking": doc.name, "docstatus": 1}, pluck="name"
	)
	lines = frappe.get_all(
		"Sales Invoice Item",
		filters={"rental_booking": doc.name, "parenttype": "Sales Invoice"},
		pluck="parent",
	)
	names = sorted(set(direct) | set(lines))
	if not names:
		return []
	rows = frappe.get_all(
		"Sales Invoice",
		filters={"name": ["in", names], "docstatus": 1, "customer": doc.customer},
		fields=[
			"name",
			"posting_date",
			"due_date",
			"grand_total",
			"outstanding_amount",
			"is_return",
			"currency",
		],
		order_by="posting_date asc",
	)
	return [{**r, "paid": flt(r.outstanding_amount) <= 0} for r in rows]


def _documents(doc, invoices: list[dict]) -> list[dict]:
	out = [{"kind": "invoice", "ref": i["name"], "label": i["name"]} for i in invoices]
	contract = doc.get("rental_contract")
	if contract and frappe.db.get_value("Rental Contract", contract, "signed_pdf"):
		out.append({"kind": "contract", "ref": contract, "label": _("Signed contract {0}").format(contract)})
	return out


def _can(doc) -> dict:
	held = doc.docstatus == 0 and doc.status == "Hold"
	confirmed = doc.docstatus == 1 and doc.status == "Confirmed"
	return {"change": held, "cancel": held or confirmed}


def detail(name: str) -> dict:
	doc = checkout.own_booking(name)
	with checkout._as_system():
		summary = checkout.booking_summary(doc)
		invoices = booking_invoices(doc)
		payments = frappe.get_all(
			"Rental Payment",
			filters={"rental_booking": name},
			fields=["name", "purpose", "status", "amount", "currency", "paid_on", "creation"],
			order_by="creation desc",
		)
		documents = _documents(doc, invoices)
	can = _can(doc)
	return {
		**summary,
		"invoices": invoices,
		"payments": payments,
		"documents": documents,
		"balance_due": sum(flt(i["outstanding_amount"]) for i in invoices if not i["is_return"]),
		"can_change": can["change"],
		"can_cancel": can["cancel"],
	}


def change(name: str, from_datetime, to_datetime) -> dict:
	doc = checkout.own_booking(name)
	if not _can(doc)["change"]:
		frappe.throw(_("Only a held booking can be changed. Cancel and book again instead."))
	with checkout._as_system():  # the customer's own held booking (own_booking above)
		timeline.move_booking(doc, from_datetime, to_datetime)
		doc.reload()
		booking_service.apply_pricing(doc)
		doc.save()
	return detail(name)


def cancel_preview(name: str) -> dict:
	doc = checkout.own_booking(name)
	if not _can(doc)["cancel"]:
		frappe.throw(_("This booking can no longer be cancelled online"))
	if doc.docstatus == 0:
		return {"policy": None, "kept": 0, "refund": 0, "fee": 0, "held": True}
	with checkout._as_system():
		return cancellation.preview(doc, by="customer")


def cancel(name: str) -> dict:
	doc = checkout.own_booking(name)
	if not _can(doc)["cancel"]:
		frappe.throw(_("This booking can no longer be cancelled online"))
	with checkout._as_system():  # the customer's own booking, cancelled under its policy
		if doc.docstatus == 1:
			result = cancellation.cancel(doc, by="customer")
		else:
			lifecycle.cancel(doc)
			result = {"kept": 0, "refund": 0}
	return {**detail(name), "cancellation": result}


def download(name: str, kind: str, ref: str) -> None:
	"""Put the PDF of one of this booking's documents on the response."""
	doc = checkout.own_booking(name)
	with checkout._as_system():
		if kind == "invoice":
			allowed = {i["name"] for i in booking_invoices(doc)}
			if ref not in allowed:
				frappe.throw(_("Document not found"), frappe.DoesNotExistError)
			content, filename = frappe.get_print("Sales Invoice", ref, as_pdf=True), f"{ref}.pdf"
		elif kind == "contract":
			if ref != doc.get("rental_contract"):
				frappe.throw(_("Document not found"), frappe.DoesNotExistError)
			url = frappe.db.get_value("Rental Contract", ref, "signed_pdf")
			if not url:
				frappe.throw(_("Document not found"), frappe.DoesNotExistError)
			file = frappe.get_doc("File", {"file_url": url})
			content, filename = file.get_content(), file.file_name
		else:
			frappe.throw(_("Document not found"), frappe.DoesNotExistError)
	frappe.local.response.filename = filename
	frappe.local.response.filecontent = content
	frappe.local.response.type = "pdf"

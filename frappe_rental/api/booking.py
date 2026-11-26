import json

import frappe
from frappe import _

from frappe_rental.services import booking as booking_service
from frappe_rental.services import booking_views, erpnext_sync, lifecycle


@frappe.whitelist()
def quote(booking: str | dict) -> dict:
	"""Price a draft booking without saving it. Returns lines, charges and totals."""
	if not frappe.has_permission("Rental Booking", "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	data = json.loads(booking) if isinstance(booking, str) else booking
	if not isinstance(data, dict) or not data.get("lines"):
		frappe.throw(_("A booking with at least one line is required"))
	data = {k: v for k, v in data.items() if k not in ("name", "docstatus", "doctype")}
	doc = frappe.get_doc({"doctype": "Rental Booking", **data})
	booking_service.validate_booking(doc)
	booking_service.apply_pricing(doc)
	return {
		"lines": [
			{
				f: line.get(f)
				for f in (
					"rental_item",
					"rental_unit",
					"qty",
					"time_unit",
					"units",
					"rate",
					"discount_amount",
					"amount",
					"applied_rule",
				)
			}
			for line in doc.lines
		],
		"charges": [{"charge": c.charge, "amount": c.amount} for c in doc.charges],
		**{
			f: doc.get(f) for f in ("currency", "net_total", "total_taxes", "grand_total", "deposit_required")
		},
	}


def _get(name: str, ptype: str):
	if not isinstance(name, str) or not name:
		frappe.throw(_("A booking name is required"))
	doc = frappe.get_doc("Rental Booking", name)
	if not frappe.has_permission("Rental Booking", ptype, doc):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return doc


def _state(doc) -> dict:
	return {"name": doc.name, "status": doc.status, "hold_expires_on": doc.hold_expires_on}


@frappe.whitelist(methods=["POST"])
def create_hold(name: str) -> dict:
	"""Hold a saved draft booking: reserve its units until the hold expires."""
	doc = _get(name, "write")
	lifecycle.place_hold(doc)
	return _state(doc)


@frappe.whitelist(methods=["POST"])
def confirm(name: str) -> dict:
	"""Confirm (submit) a booking after the deposit, contract and availability guards."""
	doc = _get(name, "submit")
	doc.submit()
	return _state(doc)


@frappe.whitelist(methods=["POST"])
def cancel(name: str) -> dict:
	"""Cancel a confirmed booking or release a hold."""
	doc = _get(name, "cancel" if frappe.db.get_value("Rental Booking", name, "docstatus") == 1 else "write")
	lifecycle.cancel(doc)
	return _state(doc)


@frappe.whitelist(methods=["POST"])
def make_invoice(name: str, submit: int = 1) -> dict:
	"""Create (or return) the one-off Sales Invoice for a confirmed booking."""
	doc = _get(name, "read")
	if not frappe.has_permission("Sales Invoice", "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	invoice = erpnext_sync.make_sales_invoice(doc, submit=bool(int(submit)))
	return {"name": doc.name, "sales_order": doc.sales_order, "sales_invoice": invoice}


def _dict_arg(value, label: str) -> dict:
	data = json.loads(value) if isinstance(value, str) and value else (value or {})
	if not isinstance(data, dict):
		frappe.throw(_("{0} must be an object").format(label))
	return data


def _require_read() -> None:
	if not frappe.has_permission("Rental Booking", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def get_list(
	filters: str | dict | None = None,
	order_by: str = "creation",
	order: str = "desc",
	start: int = 0,
	page_length: int = 20,
	group_by: str | None = None,
) -> dict:
	"""Bookings list for the staff app: one page of rows, the total, and group counts when asked."""
	_require_read()
	f = _dict_arg(filters, _("Filters"))
	out = booking_views.list_bookings(f, order_by, order, start, page_length)
	if group_by:
		out["groups"] = booking_views.group_counts(group_by, f)
	return out


@frappe.whitelist()
def get_detail(name: str) -> dict:
	"""Everything the booking page shows: fields, lines, totals, linked documents, activity and allowed actions."""
	return booking_views.get_detail(_get(name, "read"))


@frappe.whitelist()
def list_options() -> dict:
	"""Filter and form choices for the staff app."""
	_require_read()
	return booking_views.options()


@frappe.whitelist(methods=["POST"])
def create(booking: str | dict, hold: int = 0) -> dict:
	"""Create a draft booking from the staff app, and optionally hold it straight away."""
	if not frappe.has_permission("Rental Booking", "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	name = booking_views.create_booking(_dict_arg(booking, _("Booking")))
	doc = frappe.get_doc("Rental Booking", name)
	if int(hold):
		lifecycle.place_hold(doc)
	return _state(doc)


LINK_SEARCH = {
	"Customer": ("customer_name", {"disabled": 0}),
	"Rental Item": ("item_name", {}),
	"Rental Unit": ("unit_name", {}),
}


@frappe.whitelist()
def search_link(doctype: str, txt: str = "", rental_item: str | None = None) -> list[dict]:
	"""Options for the create form's pickers. Only the doctypes the form uses, through permission-aware get_list."""
	if doctype not in LINK_SEARCH:
		frappe.throw(_("Search on {0} is not allowed").format(doctype))
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	title, filters = LINK_SEARCH[doctype]
	filters = dict(filters)
	if doctype == "Rental Unit" and rental_item:
		filters["rental_item"] = rental_item
	like = f"%{txt or ''}%"
	rows = frappe.get_list(
		doctype,
		fields=["name", f"{title} as title"],
		filters=filters,
		or_filters=[[doctype, "name", "like", like], [doctype, title, "like", like]],
		order_by="modified desc",
		limit_page_length=20,
	)
	return [{"value": r.name, "label": r.title or r.name} for r in rows]


@frappe.whitelist(methods=["POST"])
def move(name: str, from_datetime: str, to_datetime: str, rental_unit: str | None = None) -> dict:
	"""Move a draft or held booking (calendar drag). Rejected when the target unit or period is taken."""
	from frappe_rental.services import timeline

	doc = _get(name, "write")
	timeline.move_booking(doc, from_datetime, to_datetime, rental_unit or None)
	return {**_state(doc), "from_datetime": doc.from_datetime, "to_datetime": doc.to_datetime}

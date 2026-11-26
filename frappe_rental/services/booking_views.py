"""Read models for the staff app bookings screens (T18): list, group counts and the detail payload.

Every read goes through ``frappe.get_list`` (permission aware) for the parent. Child rows and link titles are fetched
only for parents the user may already read.
"""

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime

STATUSES = ("Draft", "Hold", "Confirmed", "Checked Out", "Returned", "Closed", "Cancelled", "No Show")
FILTER_FIELDS = ("status", "rental_type", "location", "customer", "company")
GROUP_FIELDS = ("status", "rental_type", "location", "customer")
SORT_FIELDS = ("creation", "modified", "from_datetime", "to_datetime", "grand_total", "name")
LIST_FIELDS = (
	"name",
	"customer",
	"rental_type",
	"location",
	"status",
	"from_datetime",
	"to_datetime",
	"currency",
	"grand_total",
	"docstatus",
)
MAX_PAGE = 500


def _filters(filters: dict | None) -> list:
	out = []
	for key, value in (filters or {}).items():
		if value in (None, ""):
			continue
		if key in FILTER_FIELDS:
			if key == "status" and value not in STATUSES:
				frappe.throw(_("Unknown status {0}").format(value))
			out.append(["Rental Booking", key, "=", value])
		elif key == "from_date":
			out.append(["Rental Booking", "to_datetime", ">=", get_datetime(value)])
		elif key == "to_date":
			out.append(["Rental Booking", "from_datetime", "<=", get_datetime(f"{value} 23:59:59")])
		elif key != "search":
			frappe.throw(_("Filter {0} is not allowed").format(key))
	return out


def _search_or(filters: dict | None) -> list | None:
	text = (filters or {}).get("search")
	if not text:
		return None
	like = f"%{text}%"
	return [["Rental Booking", "name", "like", like], ["Rental Booking", "customer", "like", like]]


def list_bookings(
	filters: dict | None = None,
	order_by: str = "creation",
	order: str = "desc",
	start: int = 0,
	page_length: int = 20,
) -> dict:
	"""Return a page of bookings with the first line's item for each, plus the total count."""
	if order_by not in SORT_FIELDS:
		frappe.throw(_("Sort field {0} is not allowed").format(order_by))
	if order not in ("asc", "desc"):
		frappe.throw(_("Sort order must be asc or desc"))
	page_length = max(1, min(cint(page_length) or 20, MAX_PAGE))
	where, or_where = _filters(filters), _search_or(filters)
	rows = frappe.get_list(
		"Rental Booking",
		fields=list(LIST_FIELDS),
		filters=where,
		or_filters=or_where,
		order_by=f"`tabRental Booking`.`{order_by}` {order}",
		start=cint(start),
		page_length=page_length,
	)
	total = len(
		frappe.get_list(
			"Rental Booking", filters=where, or_filters=or_where, pluck="name", limit_page_length=0
		)
	)
	_attach_items(rows)
	_attach_titles(rows)
	return {"rows": rows, "total": total}


def group_counts(group_by: str, filters: dict | None = None) -> list[dict]:
	"""Count readable bookings per value of ``group_by``."""
	if group_by not in GROUP_FIELDS:
		frappe.throw(_("Group by {0} is not allowed").format(group_by))
	# Counted in Python: aggregate syntax in get_list differs between v15 and v16.
	values = frappe.get_list(
		"Rental Booking",
		filters=_filters(filters),
		or_filters=_search_or(filters),
		pluck=group_by,
		limit_page_length=0,
	)
	counts: dict = {}
	for v in values:
		counts[v] = counts.get(v, 0) + 1
	return [{"value": k, "count": n} for k, n in sorted(counts.items(), key=lambda kv: -kv[1])]


def _attach_items(rows: list) -> None:
	names = [r.name for r in rows]
	if not names:
		return
	# Child rows of parents the user may already read (checked by get_list above), so no second check.
	lines = frappe.get_all(
		"Rental Booking Line",
		filters={"parent": ["in", names], "parenttype": "Rental Booking"},
		fields=["parent", "rental_item", "rental_unit", "idx"],
		order_by="idx asc",
	)
	titles = _titles("Rental Item", "item_name", {ln.rental_item for ln in lines})
	first, count = {}, {}
	for ln in lines:
		count[ln.parent] = count.get(ln.parent, 0) + 1
		first.setdefault(ln.parent, ln)
	for r in rows:
		ln = first.get(r.name)
		r.item = titles.get(ln.rental_item, ln.rental_item) if ln else None
		r.line_count = count.get(r.name, 0)


def _attach_titles(rows: list) -> None:
	customers = _titles("Customer", "customer_name", {r.customer for r in rows})
	for r in rows:
		r.customer_name = customers.get(r.customer, r.customer)


def _titles(doctype: str, field: str, names: set) -> dict:
	names = [n for n in names if n]
	if not names:
		return {}
	return dict(
		frappe.get_all(doctype, filters={"name": ["in", names]}, fields=["name", field], as_list=True)
	)


def get_detail(doc) -> dict:
	"""Detail payload for one booking the caller may read: fields, lines, charges, links and activity."""
	item_titles = _titles("Rental Item", "item_name", {ln.rental_item for ln in doc.lines})
	unit_titles = _titles("Rental Unit", "unit_name", {ln.rental_unit for ln in doc.lines})
	fields = (
		"name",
		"customer",
		"contact",
		"rental_type",
		"location",
		"source",
		"status",
		"docstatus",
		"from_datetime",
		"to_datetime",
		"hold_expires_on",
		"company",
		"currency",
		"net_total",
		"total_taxes",
		"grand_total",
		"deposit_required",
		"deposit_paid",
		"balance",
		"taxes_and_charges",
		"coupon_code",
	)
	out = {f: doc.get(f) for f in fields}
	out["customer_name"] = frappe.db.get_value("Customer", doc.customer, "customer_name") or doc.customer
	out["lines"] = [
		{
			"rental_item": ln.rental_item,
			"item_name": item_titles.get(ln.rental_item, ln.rental_item),
			"rental_unit": ln.rental_unit,
			"unit_name": unit_titles.get(ln.rental_unit, ln.rental_unit),
			"qty": ln.qty,
			"time_unit": ln.time_unit,
			"units": ln.units,
			"rate": ln.rate,
			"discount_amount": ln.discount_amount,
			"amount": ln.amount,
		}
		for ln in doc.lines
	]
	out["charges"] = [
		{"charge": c.charge, "description": c.description, "amount": c.amount} for c in doc.charges
	]
	out["links"] = [
		{"doctype": dt, "name": doc.get(f)}
		for dt, f in (
			("Sales Order", "sales_order"),
			("Sales Invoice", "sales_invoice"),
			("Contract", "contract"),
		)
		if doc.get(f)
	]
	out["activity"] = activity(doc)
	out["actions"] = actions(doc)
	# Activity times are shown relative to this, so the browser timezone does not matter.
	out["server_now"] = now_datetime()
	return out


def activity(doc, limit: int = 20) -> list[dict]:
	"""Status changes (from Version) and comments, newest first."""
	events = []
	for v in frappe.get_all(
		"Version",
		filters={"ref_doctype": doc.doctype, "docname": doc.name},
		fields=["data", "creation", "owner"],
		order_by="creation desc",
		limit=limit,
	):
		data = frappe.parse_json(v.data or "{}")
		for field, _old, new in data.get("changed", []):
			if field == "status":
				events.append(
					{"text": _("Status set to {0}").format(_(new)), "at": v.creation, "by": v.owner}
				)
	for c in frappe.get_all(
		"Comment",
		filters={"reference_doctype": doc.doctype, "reference_name": doc.name, "comment_type": "Comment"},
		fields=["content", "creation", "owner"],
		order_by="creation desc",
		limit=limit,
	):
		events.append({"text": frappe.utils.strip_html(c.content or ""), "at": c.creation, "by": c.owner})
	events.append({"text": _("Booking created"), "at": doc.creation, "by": doc.owner})
	events.sort(key=lambda e: get_datetime(e["at"]), reverse=True)
	return events[:limit]


def actions(doc) -> list[str]:
	"""Lifecycle actions the current user may take now."""
	out = []
	if doc.docstatus == 0:
		if frappe.has_permission("Rental Booking", "write", doc) and doc.status != "Hold":
			out.append("hold")
		if frappe.has_permission("Rental Booking", "submit", doc):
			out.append("confirm")
		if doc.status == "Hold" and frappe.has_permission("Rental Booking", "write", doc):
			out.append("cancel")
	elif doc.docstatus == 1:
		if frappe.has_permission("Rental Booking", "cancel", doc):
			out.append("cancel")
		if not doc.sales_invoice and frappe.has_permission("Sales Invoice", "create"):
			out.append("invoice")
	return out


def options() -> dict:
	"""Values for the list filters and the create form."""
	return {
		"statuses": list(STATUSES),
		"rental_types": frappe.get_list("Rental Type", pluck="name", order_by="name asc"),
		"locations": frappe.get_list("Rental Location", pluck="name", order_by="name asc"),
		"group_fields": list(GROUP_FIELDS),
		"sort_fields": list(SORT_FIELDS),
	}


def create_booking(data: dict) -> str:
	"""Insert a draft booking from the create form. Only booking fields the form offers are accepted."""
	allowed = ("customer", "rental_type", "location", "from_datetime", "to_datetime", "coupon_code", "source")
	lines = data.get("lines") or []
	if not lines:
		frappe.throw(_("Add at least one item"))
	doc = frappe.get_doc(
		{
			"doctype": "Rental Booking",
			**{k: data.get(k) for k in allowed if data.get(k)},
			"lines": [
				{k: ln.get(k) for k in ("rental_item", "rental_unit", "qty") if ln.get(k)} for ln in lines
			],
		}
	)
	doc.insert()
	return doc.name

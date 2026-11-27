"""Contract screens (T47): staff list and detail tabs, and the customer's own contracts.

Staff go through normal permissions (``frappe.get_list`` and ``has_permission``). Customers have none on
Rental Contract, so their calls resolve the contract through ``customer_contract``: its customer must be one
the user acts for (``checkout.my_customers``) and it must have left Draft, otherwise it looks like not found.
"""

import frappe
from frappe import _
from frappe.utils import cint

from frappe_rental.services import checkout, esign

LIST_FIELDS = [
	"name",
	"customer",
	"rental_type",
	"status",
	"start_date",
	"end_date",
	"open_ended",
	"currency",
	"signed_on",
	"countersigned_on",
]
# What a customer may see: nothing before the contract is offered to them.
CUSTOMER_STATUSES = ("Awaiting Signature", "Active", "Suspended", "Ending", "Ended", "Terminated", "Renewed")


def _with_names(rows) -> list:
	names = {r.customer for r in rows}
	titles = (
		dict(
			frappe.get_all(
				"Customer",
				filters={"name": ["in", list(names)]},
				fields=["name", "customer_name"],
				as_list=True,
			)
		)
		if names
		else {}
	)
	for r in rows:
		r["customer_name"] = titles.get(r.customer) or r.customer
	return rows


def listing(status=None, search=None, start=0, page_length=20) -> dict:
	if not frappe.has_permission("Rental Contract", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	filters = {"status": status} if status else {}
	or_filters = None
	if search:
		like = f"%{search}%"
		or_filters = [["name", "like", like], ["customer", "like", like]]
		customers = frappe.get_all("Customer", filters={"customer_name": ["like", like]}, pluck="name")
		if customers:
			or_filters.append(["customer", "in", customers])
	rows = frappe.get_list(
		"Rental Contract",
		filters=filters,
		or_filters=or_filters,
		fields=LIST_FIELDS,
		order_by="modified desc",
		start=cint(start),
		page_length=max(1, min(cint(page_length) or 20, 100)),
	)
	return {
		"rows": _with_names(rows),
		"total": len(
			frappe.get_list(
				"Rental Contract", filters=filters, or_filters=or_filters, pluck="name", limit=10000
			)
		),
	}


def _plan(doc):
	plan = (doc.get("billing_plan") or [None])[0]
	return plan.as_dict() if plan else None


def _bookings(doc) -> list[dict]:
	rows = frappe.get_all(
		"Rental Booking",
		filters={"rental_contract": doc.name, "docstatus": ["<", 2]},
		fields=["name", "status", "from_datetime", "to_datetime", "grand_total", "currency"],
		order_by="from_datetime asc",
	)
	return rows


def _visits(doc) -> list[dict]:
	return [
		{
			k: v.get(k)
			for k in (
				"name",
				"planned_date",
				"visit_type",
				"status",
				"technician",
				"rental_booking",
				"response_due",
				"resolution_due",
				"completed_on",
				"sla_breached",
				"notes",
			)
		}
		for v in doc.get("visits") or []
	]


def _allocations(doc) -> list[dict]:
	return [
		{
			k: a.get(k)
			for k in (
				"name",
				"allocation_type",
				"rental_item",
				"rental_unit",
				"from_date",
				"to_date",
				"qty",
				"capacity",
				"capacity_used",
				"exclusive",
				"status",
			)
		}
		for a in doc.get("allocations") or []
	]


def _overview(doc) -> dict:
	fields = (
		"customer",
		"rental_type",
		"status",
		"currency",
		"start_date",
		"end_date",
		"open_ended",
		"minimum_term_months",
		"auto_renew",
		"renewal_term_months",
		"notice_period_days",
		"early_termination_fee",
		"price_lock_months",
		"indexation_percent",
		"included_allowance",
		"allowance_unit",
		"overage_rate",
		"sla_response_hours",
		"sla_resolution_hours",
		"visit_frequency",
		"signed_by",
		"signed_on",
		"countersigned_by",
		"countersigned_on",
		"terminated_on",
		"termination_reason",
		"renewal_of",
	)
	out = {f: doc.get(f) for f in fields}
	out["customer_name"] = frappe.db.get_value("Customer", doc.customer, "customer_name") or doc.customer
	return out


def detail(name: str) -> dict:
	"""Every tab of the staff contract screen."""
	doc = frappe.get_doc("Rental Contract", name)
	if not frappe.has_permission("Rental Contract", "read", doc):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	can_write = frappe.has_permission("Rental Contract", "write", doc)
	return {
		"name": doc.name,
		**_overview(doc),
		"terms": {
			"html": doc.rendered_terms,
			"template": doc.terms_template,
			"version": doc.template_version,
		},
		"allocations": _allocations(doc),
		"billing": {"plan": _plan(doc), "bookings": _bookings(doc)},
		"visits": _visits(doc),
		"amendments": [
			{"effective_date": a.get("effective_date"), "reason": a.get("reason")}
			for a in doc.get("amendments") or []
		],
		"actions": {
			"send_for_signature": can_write and doc.status in ("Draft", "In Review"),
			"countersign": can_write and doc.status == "Awaiting Signature" and bool(doc.signed_on),
		},
	}


def customer_contract(name: str):
	"""The contract, if it belongs to a customer the session user acts for and has been offered to them."""
	if not name or not frappe.db.exists("Rental Contract", name):
		frappe.throw(_("Contract not found"), frappe.DoesNotExistError)
	doc = frappe.get_doc("Rental Contract", name)
	if doc.customer not in checkout.my_customers() or doc.status not in CUSTOMER_STATUSES:
		frappe.throw(_("Contract not found"), frappe.DoesNotExistError)
	return doc


def my_listing() -> dict:
	customers = checkout.my_customers()
	if not customers:
		return {"rows": []}
	with checkout._as_system():  # scoped to the user's own customers above
		rows = frappe.get_all(
			"Rental Contract",
			filters={"customer": ["in", customers], "status": ["in", list(CUSTOMER_STATUSES)]},
			fields=LIST_FIELDS,
			order_by="start_date desc",
		)
	return {"rows": rows}


def my_detail(name: str) -> dict:
	doc = customer_contract(name)
	with checkout._as_system():
		visits = _visits(doc)
		allocations = _allocations(doc)
	return {
		"name": doc.name,
		**_overview(doc),
		"terms_html": doc.rendered_terms,
		"require_otp": bool(doc.require_otp),
		"awaiting_signature": doc.status == "Awaiting Signature" and not doc.signed_on,
		"signed": bool(doc.signed_on),
		"can_request_service": doc.status in ("Active", "Suspended", "Ending"),
		"allocations": allocations,
		"visits": [
			{k: v[k] for k in ("planned_date", "visit_type", "status", "completed_on", "notes")}
			for v in visits
		],
		"has_pdf": bool(doc.signed_pdf),
		"can_sign": esign.can_sign_for(doc.customer),
	}


def download(name: str) -> None:
	"""Put the signed PDF of one of this customer's contracts on the response."""
	doc = customer_contract(name)
	if not doc.signed_pdf:
		frappe.throw(_("Document not found"), frappe.DoesNotExistError)
	with checkout._as_system():
		file = frappe.get_doc("File", {"file_url": doc.signed_pdf})
		content, filename = file.get_content(), file.file_name
	frappe.local.response.filename = filename
	frappe.local.response.filecontent = content
	frappe.local.response.type = "pdf"

"""Billing plan resolution and schedule upkeep on bookings (T22, D6).

The maths lives in `billing_schedule` (pure). This module reads documents and writes child rows.
Plan precedence (D6 rule 1): booking plan, then its Rental Contract's plan, then the Rental Type
default, then a one-off plan.
"""

from datetime import time, timedelta

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, getdate

from frappe_rental.services import billing_schedule

PLAN_FIELDS = (
	"frequency",
	"interval",
	"interval_unit",
	"milestone_percents",
	"timing",
	"first_invoice",
	"first_invoice_date",
	"alignment",
	"alignment_day",
	"proration",
	"amount_basis",
	"period_amount",
)
LOCKED = ("Invoiced", "Paid", "Credited")
DEFAULT_PLAN = {"frequency": "One-off", "timing": "At confirmation"}


def _row_dict(row) -> dict:
	return {f: row.get(f) for f in PLAN_FIELDS}


def resolve_plan(doc) -> dict:
	if doc.get("billing_plan"):
		return _row_dict(doc.billing_plan[0])
	contract = doc.get("rental_contract")
	if contract:
		rows = frappe.get_all(
			"Rental Billing Plan",
			filters={"parent": contract, "parenttype": "Rental Contract", "parentfield": "billing_plan"},
			fields=list(PLAN_FIELDS),
			limit=1,
		)
		if rows:
			return rows[0]
	if doc.get("rental_type"):
		rows = frappe.get_all(
			"Rental Billing Plan",
			filters={"parent": doc.rental_type, "parenttype": "Rental Type", "parentfield": "billing_plan"},
			fields=list(PLAN_FIELDS),
			limit=1,
		)
		if rows:
			return rows[0]
	return dict(DEFAULT_PLAN)


def _precision(doc) -> int:
	return cint(frappe.get_precision("Rental Billing Schedule", "amount")) or 2


def _needs_rebuild(doc) -> bool:
	if not doc.get("billing_schedule"):
		return True
	before = doc.get_doc_before_save()
	if not before:
		return False
	return (
		before.from_datetime != doc.from_datetime
		or before.to_datetime != doc.to_datetime
		or flt(before.net_total) != flt(doc.net_total)
		or [_row_dict(r) for r in before.get("billing_plan") or []]
		!= [_row_dict(r) for r in doc.get("billing_plan") or []]
	)


def update_schedule(doc, force: bool = False) -> None:
	"""Validate hook: rebuild the un-invoiced schedule rows when dates, total or plan changed.

	Manual edits to planned rows survive saves that change none of those. Invoiced rows are kept.
	"""
	if len(doc.get("billing_plan") or []) > 1:
		frappe.throw(_("A booking has one billing plan row"))
	if not doc.from_datetime or not doc.to_datetime:
		return
	if not force and not _needs_rebuild(doc):
		return
	plan = resolve_plan(doc)
	start, end = getdate(doc.from_datetime), getdate(doc.to_datetime)
	if end > start and get_datetime(doc.to_datetime).time() == time(0, 0):
		end -= timedelta(days=1)  # a booking ending at midnight does not bill that day
	existing = [r.as_dict() for r in doc.get("billing_schedule") or []]
	try:
		rows = billing_schedule.regenerate(
			existing,
			plan,
			start,
			end,
			flt(doc.net_total),
			confirmed_on=getdate(doc.modified) if doc.docstatus == 1 else None,
			precision=_precision(doc),
		)
	except billing_schedule.BillingPlanError as e:
		frappe.throw(_("Billing plan: {0}").format(_(str(e))))
	kept = [r for r in doc.get("billing_schedule") or [] if r.status in LOCKED]
	doc.set("billing_schedule", kept)
	for r in rows:
		doc.append("billing_schedule", {**r, "status": "Planned"})


def preview(doc_or_dict, plan: dict | None = None) -> list[dict]:
	"""Schedule a booking would get, without saving (API and Billing tab)."""
	doc = frappe._dict(doc_or_dict) if isinstance(doc_or_dict, dict) else doc_or_dict
	plan = plan or resolve_plan(doc)
	start, end = getdate(doc.from_datetime), getdate(doc.to_datetime)
	if end > start and get_datetime(doc.to_datetime).time() == time(0, 0):
		end -= timedelta(days=1)
	return billing_schedule.generate(plan, start, end, flt(doc.net_total))

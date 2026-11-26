"""Rental Contract core (T40, docs/CONTRACTS.md D7): structured terms, lifecycle, snapshot, amendments.

Lifecycle: Draft -> In Review -> Awaiting Signature -> Active -> (Suspended) -> Ending -> Ended |
Terminated | Renewed. Moves go through `transition()`, which checks the allowed map below.

- `send_for_signature` renders the terms (template + clause overrides + merge fields) into
  `rendered_terms` with the template version. From then on the snapshot never changes with the
  template: only `amend()` re-renders, and it keeps the previous text on the amendment row.
- `activate` (signing; e-signature flows arrive in T41) records the signer and mirrors the contract as
  a signed ERPNext Contract, which the booking confirm guard (T14) already checks.
- While Active, the structured terms are frozen except through `amend()`.
"""

import json

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, nowdate

from frappe_rental.compat import erpnext as compat
from frappe_rental.services import terms

DOCTYPE = "Rental Contract"
ALLOWED = {
	"Draft": {"In Review", "Awaiting Signature"},
	"In Review": {"Draft", "Awaiting Signature"},
	"Awaiting Signature": {"Draft", "Active"},
	"Active": {"Suspended", "Ending", "Terminated"},
	"Suspended": {"Active", "Terminated"},
	"Ending": {"Ended", "Renewed", "Terminated", "Active"},
}
FROZEN = (
	"customer",
	"company",
	"start_date",
	"end_date",
	"open_ended",
	"auto_renew",
	"renewal_term_months",
	"notice_period_days",
	"minimum_term_months",
	"early_termination_fee",
	"deposit_rule",
	"cancellation_policy",
	"price_lock_months",
	"indexation_percent",
	"included_allowance",
	"allowance_unit",
	"overage_rate",
	"insurance_required",
	"damage_liability_cap",
	"maintenance_responsibility",
	"sla_response_hours",
	"sla_resolution_hours",
	"visit_frequency",
	"terms_template",
)
SIGNED = ("Active", "Suspended", "Ending", "Ended", "Terminated", "Renewed")


def validate(doc) -> None:
	if not doc.open_ended and doc.end_date and getdate(doc.end_date) < getdate(doc.start_date):
		frappe.throw(_("The contract ends before it starts"))
	if not doc.open_ended and not doc.end_date:
		frappe.throw(_("Set an end date or mark the contract open-ended"))
	if len(doc.get("billing_plan") or []) > 1:
		frappe.throw(_("A contract has one billing plan row"))
	if doc.terms_template and doc.clauses:
		missing = terms.mandatory_missing(doc.terms_template, [{"clause": c.clause} for c in doc.clauses])
		if missing:
			frappe.throw(_("Mandatory clauses cannot be removed: {0}").format(", ".join(missing)))
	if not doc.terms_template and doc.rental_type:
		doc.terms_template = terms.template_for(doc.rental_type, doc.language)
	before = doc.get_doc_before_save()
	if before and before.signed_on:
		for f in ("signed_by", "signature", "signature_type", "signer_ip", "signed_on"):
			if str(before.get(f) or "") != str(doc.get(f) or "") and not doc.flags.activating:
				frappe.throw(_("Signature details cannot change"))
	if before and before.status in SIGNED and not doc.flags.amending:
		changed = [f for f in FROZEN if str(before.get(f) or "") != str(doc.get(f) or "")]
		if changed or before.rendered_terms != doc.rendered_terms:
			frappe.throw(
				_("A signed contract changes only by amendment ({0})").format(", ".join(changed) or "terms")
			)


def transition(doc, status: str) -> None:
	if status not in ALLOWED.get(doc.status, set()):
		frappe.throw(_("A {0} contract cannot become {1}").format(_(doc.status), _(status)))
	doc.status = status
	doc.save()


def context(doc) -> dict:
	"""Merge fields for rendering the contract's terms."""
	plan = doc.billing_plan[0].as_dict() if doc.get("billing_plan") else frappe._dict()
	deposit = 0
	if doc.deposit_rule:
		rule = frappe.get_cached_doc("Rental Deposit Rule", doc.deposit_rule)
		deposit = rule.amount if rule.deposit_type == "Fixed" else f"{rule.percent}%"
	return {
		"customer": frappe.get_doc("Customer", doc.customer),
		"contract": doc,
		"units": [a.as_dict() for a in doc.get("allocations") or []],
		"billing_plan": plan,
		"deposit": deposit,
	}


def render(doc) -> dict:
	if not doc.terms_template:
		frappe.throw(_("Choose a terms template"))
	overrides = [{"clause": c.clause, "body": c.body} for c in doc.clauses] if doc.clauses else None
	return terms.render(doc.terms_template, context(doc), overrides)


def send_for_signature(doc) -> None:
	out = render(doc)
	doc.rendered_terms = out["html"]
	doc.template_version = out["version"]
	transition(doc, "Awaiting Signature")


def activate(doc, signed_by: str, countersigned_by: str | None = None) -> str:
	"""Record the signature, mirror it as a signed ERPNext Contract and make the contract Active."""
	if doc.status != "Awaiting Signature":
		frappe.throw(_("Send the contract for signature first"))
	if not doc.rendered_terms:
		frappe.throw(_("The contract has no rendered terms"))
	now = now_datetime()
	doc.signed_by = signed_by
	doc.signed_on = doc.signed_on or now
	doc.flags.activating = True
	if countersigned_by:
		doc.countersigned_by, doc.countersigned_on = countersigned_by, now
	if not doc.erpnext_contract:
		doc.erpnext_contract = compat.make_signed_contract(
			doc.customer,
			doc.start_date,
			None if doc.open_ended else doc.end_date,
			doc.rendered_terms,
			signed_by,
			now,
		)
	transition(doc, "Active")
	return doc.erpnext_contract


def amend(doc, reason: str, effective_date=None, changes: dict | None = None) -> None:
	"""Change a signed contract: apply `changes`, re-render, and keep the old text on an amendment row."""
	if doc.status not in ("Active", "Suspended", "Ending"):
		frappe.throw(_("Only a signed, running contract is amended"))
	if not reason:
		frappe.throw(_("Give a reason for the amendment"))
	changes = changes or {}
	bad = [k for k in changes if k not in FROZEN]
	if bad:
		frappe.throw(_("These fields are not contract terms: {0}").format(", ".join(bad)))
	previous = doc.rendered_terms
	doc.update(changes)
	out = render(doc)
	doc.rendered_terms = out["html"]
	doc.template_version = out["version"]
	doc.append(
		"amendments",
		{
			"effective_date": effective_date or nowdate(),
			"reason": reason,
			"version": len(doc.amendments) + 1,
			"changes": json.dumps(changes, default=str),
			"previous_terms": previous,
		},
	)
	doc.flags.amending = True
	doc.save()


def terminate(doc, reason: str, on=None) -> None:
	"""End early. The termination fee becomes a Billable Event in T44."""
	if not reason:
		frappe.throw(_("Give a reason for the termination"))
	doc.terminated_on = getdate(on or nowdate())
	doc.termination_reason = reason
	doc.flags.amending = True  # recording the end is not a change of terms
	transition(doc, "Terminated")


def for_booking(booking) -> str | None:
	"""The Rental Contract a booking falls under: its own link, else the one mirroring its ERPNext Contract."""
	if booking.get("rental_contract"):
		return booking.rental_contract
	if booking.get("contract"):
		return frappe.db.get_value(DOCTYPE, {"erpnext_contract": booking.contract})
	return None

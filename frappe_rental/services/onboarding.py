"""Native Frappe onboarding for the Rental module.

The steps are fixtures (Module Onboarding "Rental" and its Onboarding Steps). Frappe's own widget marks a
step done when the user creates the entry from the workspace; this service also marks it when the record is
created any other way (the staff app, imports, the API) so the checklist always matches the data.
"""

import frappe
from frappe import _

MODULE_ONBOARDING = "Rental"


def _steps() -> list[dict]:
	if not frappe.db.exists("Module Onboarding", MODULE_ONBOARDING):
		return []
	names = frappe.get_all(
		"Onboarding Step Map", filters={"parent": MODULE_ONBOARDING}, pluck="step", order_by="idx"
	)
	return [
		frappe.db.get_value(
			"Onboarding Step",
			n,
			["name", "title", "action", "reference_document", "is_complete"],
			as_dict=True,
		)
		for n in names
	]


def sync() -> None:
	"""Mark every Create Entry step whose DocType already has a record. Idempotent."""
	for step in _steps():
		if step.is_complete or step.action != "Create Entry" or not step.reference_document:
			continue
		if frappe.db.exists(step.reference_document, {}):
			frappe.db.set_value("Onboarding Step", step.name, "is_complete", 1, update_modified=False)
	_finish()


def _finish() -> None:
	steps = _steps()
	if steps and all(s.is_complete or s.get("is_skipped") for s in steps):
		frappe.db.set_value("Module Onboarding", MODULE_ONBOARDING, "is_complete", 1, update_modified=False)


def on_insert(doc, method=None) -> None:
	"""doc_events hook: a first record of a step's DocType completes that step."""
	for step in _steps():
		if step.reference_document == doc.doctype and not step.is_complete:
			frappe.db.set_value("Onboarding Step", step.name, "is_complete", 1, update_modified=False)
	_finish()


def status() -> dict:
	"""Checklist for the staff app: each step with its state and where to do it."""
	steps = _steps()
	return {
		"title": _("Let's Set Up Rental."),
		"steps": [
			{
				"name": s.name,
				"title": _(s.title),
				"doctype": s.reference_document,
				"done": bool(s.is_complete),
			}
			for s in steps
		],
		"done": sum(1 for s in steps if s.is_complete),
		"total": len(steps),
	}

"""Clause library and terms templates (T39, docs/CONTRACTS.md D7).

A Rental Terms Template is an introduction plus an ordered list of Rental Clauses. Rendering runs
Frappe's sandboxed Jinja over each part with merge fields (customer, contract, booking, units,
billing_plan, deposit, plus anything the caller adds). Right-to-left languages (Arabic, Hebrew,
Persian, Urdu) wrap the output in `dir="rtl"`.

Versioning: a template's `version` goes up whenever its text or clause list changes; contracts store
the rendered snapshot with the version (T40), so later edits never change a signed contract.
"""

import frappe
from frappe import _
from frappe.utils.jinja import validate_template as _frappe_validate

RTL = {"ar", "he", "fa", "ur"}


def validate_jinja(text: str | None) -> None:
	if text:
		_frappe_validate(text)


def validate_template(doc) -> None:
	validate_jinja(doc.body)
	seen = set()
	for row in doc.clauses:
		if row.clause in seen:
			frappe.throw(_("Row {0}: clause {1} is listed twice").format(row.idx, row.title or row.clause))
		seen.add(row.clause)
	if doc.is_new():
		doc.version = doc.version or 1
		return
	before = doc.get_doc_before_save()
	if before and (
		(before.body or "") != (doc.body or "")
		or [r.clause for r in before.clauses] != [r.clause for r in doc.clauses]
	):
		doc.version = (before.version or 1) + 1


def template_for(rental_type: str | None, language: str | None = None) -> str | None:
	"""Active template for a type and language, falling back to the general template, then any language."""
	candidates = []
	for rtype in ([rental_type] if rental_type else []) + [None]:
		type_filter = rtype if rtype else ["is", "not set"]
		if language:
			candidates.append({"rental_type": type_filter, "language": language})
		candidates.append({"rental_type": type_filter})
	for filters in candidates:
		name = frappe.db.get_value("Rental Terms Template", {"is_active": 1, **filters})
		if name:
			return name
	return None


def is_rtl(language: str | None) -> bool:
	return bool(language) and language.split("-")[0].lower() in RTL


def render(template: str, context: dict | None = None, clauses: list[dict] | None = None) -> dict:
	"""Render a template. `clauses` overrides the clause list: [{clause, body?}] (contract overrides).

	Returns {"html", "version", "language", "direction", "clauses": [{clause, title, html}]}.
	"""
	doc = frappe.get_doc("Rental Terms Template", template)
	ctx = frappe._dict(context or {})
	rows = clauses if clauses is not None else [{"clause": r.clause} for r in doc.clauses]
	parts, rendered = [], []
	if doc.body:
		parts.append(f'<div class="rental-terms-intro">{frappe.render_template(doc.body, ctx)}</div>')
	for row in rows:
		clause = frappe.get_cached_doc("Rental Clause", row["clause"])
		if clause.disabled:
			continue
		body = row.get("body") if row.get("body") and clause.editable_per_contract else clause.body
		html = frappe.render_template(body, ctx)
		rendered.append({"clause": clause.name, "title": clause.title, "html": html})
		parts.append(
			f'<section class="rental-clause"><h4>{frappe.utils.escape_html(clause.title)}</h4>{html}</section>'
		)
	direction = "rtl" if is_rtl(doc.language) else "ltr"
	return {
		"html": f'<div class="rental-terms" dir="{direction}">' + "".join(parts) + "</div>",
		"version": doc.version,
		"language": doc.language,
		"direction": direction,
		"clauses": rendered,
	}


def mandatory_missing(template: str, clauses: list[dict]) -> list[str]:
	"""Mandatory clauses of the template that an override list drops."""
	doc = frappe.get_doc("Rental Terms Template", template)
	kept = {c["clause"] for c in clauses}
	return [
		r.clause
		for r in doc.clauses
		if frappe.db.get_value("Rental Clause", r.clause, "mandatory") and r.clause not in kept
	]


def sample_context(customer: str | None = None) -> dict:
	"""Merge fields for a preview without a contract."""
	return {
		"customer": frappe.get_doc("Customer", customer).as_dict()
		if customer
		else frappe._dict(customer_name=_("Customer")),
		"contract": frappe._dict(start_date=frappe.utils.nowdate(), end_date=None, name=_("Preview")),
		"units": [],
		"billing_plan": frappe._dict(frequency=_("Monthly")),
		"deposit": 0,
	}

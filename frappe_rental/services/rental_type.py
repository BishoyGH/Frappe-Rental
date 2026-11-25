"""Rental Type logic (T06): custom field sync, presets and the Accounting Dimension."""

import json
import re
from pathlib import Path

import frappe
from frappe import _

FIELDNAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
# Doctypes that custom fields may target. Only those that exist are synced, so this works before
# Rental Item, Unit and Booking are added by later tasks.
CUSTOM_FIELD_TARGETS = ("Rental Item", "Rental Unit", "Rental Booking")
PRESET_FILE = Path(__file__).resolve().parent.parent / "rental" / "presets" / "types.json"
DIMENSION_LABEL = "Rental Item Type"


def validate_custom_fields(doc) -> None:
	seen = set()
	for row in doc.custom_fields or []:
		if not FIELDNAME_RE.match(row.fieldname or ""):
			frappe.throw(
				_("Row {0}: field name must be lowercase letters, digits and underscores").format(row.idx)
			)
		key = (row.applies_to, row.fieldname)
		if key in seen:
			frappe.throw(
				_("Row {0}: duplicate field {1} for {2}").format(row.idx, row.fieldname, row.applies_to)
			)
		seen.add(key)


def sync_custom_fields(doc, targets: tuple[str, ...] | None = None) -> list[str]:
	"""Create or update real Custom Fields for the type's rows. Idempotent; returns the field names touched.

	Fields are shared between types with the same fieldname, so rows are never deleted here.
	"""
	touched = []
	allowed = targets if targets is not None else CUSTOM_FIELD_TARGETS
	for row in doc.custom_fields or []:
		if row.applies_to not in allowed or not frappe.db.exists("DocType", row.applies_to):
			continue
		name = frappe.db.get_value("Custom Field", {"dt": row.applies_to, "fieldname": row.fieldname})
		values = {
			"label": row.label,
			"fieldtype": row.fieldtype,
			"options": row.options,
			"reqd": row.reqd,
			"insert_after": _last_field(row.applies_to),
			"module": "Rental",
		}
		if name:
			frappe.db.set_value(
				"Custom Field", name, {k: v for k, v in values.items() if k != "insert_after"}
			)
		else:
			frappe.get_doc(
				{"doctype": "Custom Field", "dt": row.applies_to, "fieldname": row.fieldname, **values}
			).insert(ignore_permissions=True)  # schema bootstrap from a validated Rental Type
		touched.append(row.fieldname)
	if touched:
		for dt in {r.applies_to for r in doc.custom_fields}:
			frappe.clear_cache(doctype=dt)
	return touched


def _last_field(doctype: str) -> str | None:
	meta = frappe.get_meta(doctype)
	fields = [
		f.fieldname for f in meta.fields if f.fieldtype not in ("Section Break", "Column Break", "Tab Break")
	]
	return fields[-1] if fields else None


def install_presets() -> list[str]:
	"""Create the bundled Rental Types that do not exist yet. Returns names created."""
	created = []
	for preset in json.loads(PRESET_FILE.read_text()):
		if frappe.db.exists("Rental Type", preset["type_name"]):
			continue
		frappe.get_doc({"doctype": "Rental Type", **preset}).insert(ignore_permissions=True)  # bundled data
		created.append(preset["type_name"])
	return created


def ensure_accounting_dimension() -> None:
	"""Accounting Dimension 'Rental Item Type' pointing at Rental Type, for P&L by type (D-accounting)."""
	if frappe.db.exists("Accounting Dimension", {"document_type": "Rental Type"}):
		return
	frappe.get_doc(
		{"doctype": "Accounting Dimension", "document_type": "Rental Type", "label": DIMENSION_LABEL}
	).insert(ignore_permissions=True)  # install-time bootstrap

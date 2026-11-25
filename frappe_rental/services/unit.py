"""Rental Unit identification (T08, decision D4).

Each unit is validated against its Rental Type's identification mode and can be found by any
identifier: unit code, barcode, serial number, batch, asset or an external id.
"""

import base64
import io

import frappe
import pyqrcode
from frappe import _

IDENTITY_FIELDS = ("serial_no", "batch_no", "asset")
# Which identity field each mode requires; other identity fields must be empty.
MODE_REQUIRES = {"None": None, "Asset": "asset", "Serial": "serial_no", "Batch": "batch_no", "Pooled": None}
UNIQUE_FIELDS = ("serial_no", "asset", "barcode")


def validate_unit(doc) -> None:
	mode = frappe.db.get_value("Rental Type", doc.rental_type, "identification_mode") or "None"
	doc.identification_mode = mode
	required = MODE_REQUIRES.get(mode)
	if required and not doc.get(required):
		frappe.throw(_("{0} is required for identification mode {1}").format(_label(doc, required), mode))
	for field in IDENTITY_FIELDS:
		if field != required and doc.get(field):
			frappe.throw(_("{0} must be empty for identification mode {1}").format(_label(doc, field), mode))
	if mode == "Pooled":
		if (doc.quantity_available or 0) < 1:
			frappe.throw(_("Quantity Available must be at least 1 for pooled units"))
	elif doc.quantity_available and doc.quantity_available != 1:
		frappe.throw(_("Quantity Available applies to pooled units only"))
	for field in UNIQUE_FIELDS:
		value = doc.get(field)
		if value:
			other = frappe.db.get_value("Rental Unit", {field: value, "name": ["!=", doc.name]}, "name")
			if other:
				frappe.throw(
					_("{0} {1} is already used by unit {2}").format(_label(doc, field), value, other)
				)
	_validate_external_ids(doc)


def _validate_external_ids(doc) -> None:
	seen = set()
	for row in doc.external_ids or []:
		key = (row.id_type.strip().lower(), row.id_value.strip())
		if key in seen:
			frappe.throw(_("Row {0}: duplicate identifier {1}").format(row.idx, row.id_value))
		seen.add(key)
		other = frappe.db.get_value(
			"Rental Unit Identifier",
			{
				"id_type": row.id_type,
				"id_value": row.id_value,
				"parent": ["!=", doc.name],
				"parenttype": "Rental Unit",
			},
			"parent",
		)
		if other:
			frappe.throw(_("Identifier {0} is already used by unit {1}").format(row.id_value, other))


def set_default_barcode(doc) -> None:
	if not doc.barcode:
		doc.db_set("barcode", doc.name, update_modified=False)


def find_unit(identifier: str) -> str | None:
	"""Return the Rental Unit name matching any identifier, or None."""
	identifier = (identifier or "").strip()
	if not identifier:
		return None
	if frappe.db.exists("Rental Unit", identifier):
		return identifier
	for field in ("barcode", *IDENTITY_FIELDS):
		name = frappe.db.get_value("Rental Unit", {field: identifier}, "name")
		if name:
			return name
	return frappe.db.get_value(
		"Rental Unit Identifier", {"id_value": identifier, "parenttype": "Rental Unit"}, "parent"
	)


def qr_data_uri(value: str, scale: int = 4) -> str:
	"""PNG QR code as a data URI, for labels (exposed to Jinja print formats)."""
	buffer = io.BytesIO()
	pyqrcode.create(value or "").png(buffer, scale=scale)
	return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def _label(doc, field: str) -> str:
	return _(doc.meta.get_label(field))

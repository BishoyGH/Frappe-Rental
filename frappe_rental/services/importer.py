"""CSV import for rental items, units and customers (T53).

The first row is the header. Columns are field names from the setup screens (``setup_ui.SCREENS``), the
custom fields the row's Rental Type defines, and, for units, ``id:<type>`` columns that fill the unit's
external identifiers (``id:rfid``, ``id:gps``...). Unknown columns are rejected before any row is written.

A row updates an existing record when it names one (``name`` column) or matches its natural key:
items by ``item_name``; units by ``barcode``, then ``serial_no``, then ``unit_name`` within the item;
customers by ``customer_name``. Otherwise it creates one. ``rental_item`` accepts the item's ID or its name.

Each row runs in its own savepoint, so one bad row is reported and skipped and the rest still import.
Normal doctype permissions and validation apply. Importing the same file twice changes nothing new.
"""

import csv
import io

import frappe
from frappe import _

from frappe_rental.services import setup_ui

DOCTYPES = ("Rental Item", "Rental Unit", "Customer")
ID_PREFIX = "id:"
MAX_ROWS = 5000


def parse(content: str) -> list[dict]:
	reader = csv.DictReader(io.StringIO(content.lstrip("﻿")))
	if not reader.fieldnames:
		frappe.throw(_("The file is empty"))
	rows = []
	for row in reader:
		clean = {(k or "").strip(): (v or "").strip() for k, v in row.items() if k}
		if any(clean.values()):
			rows.append(clean)
	if len(rows) > MAX_ROWS:
		frappe.throw(_("At most {0} rows can be imported at once").format(MAX_ROWS))
	return rows


def _all_custom_fields(doctype: str) -> set[str]:
	return set(
		frappe.get_all(
			"Rental Type Custom Field",
			filters={"parenttype": "Rental Type", "applies_to": doctype},
			pluck="fieldname",
		)
	)


def check_columns(doctype: str, columns) -> None:
	screen = setup_ui.SCREENS[doctype]
	allowed = set(screen["fields"]) | {"name"} | _all_custom_fields(doctype)
	unknown = [
		c for c in columns if c not in allowed and not (doctype == "Rental Unit" and c.startswith(ID_PREFIX))
	]
	if unknown:
		frappe.throw(_("Unknown columns: {0}").format(", ".join(sorted(unknown))))


def _resolve_item(value: str) -> str:
	if frappe.db.exists("Rental Item", value):
		return value
	name = frappe.db.get_value("Rental Item", {"item_name": value})
	if not name:
		frappe.throw(_("Rental Item {0} not found").format(value))
	return name


def find_existing(doctype: str, row: dict) -> str | None:
	if row.get("name"):
		if not frappe.db.exists(doctype, row["name"]):
			frappe.throw(_("{0} {1} not found").format(_(doctype), row["name"]))
		return row["name"]
	if doctype == "Rental Item" and row.get("item_name"):
		return frappe.db.get_value("Rental Item", {"item_name": row["item_name"]})
	if doctype == "Customer" and row.get("customer_name"):
		return frappe.db.get_value("Customer", {"customer_name": row["customer_name"]})
	if doctype == "Rental Unit":
		for key in ("barcode", "serial_no"):
			if row.get(key):
				found = frappe.db.get_value("Rental Unit", {key: row[key]})
				if found:
					return found
		if row.get("unit_name") and row.get("rental_item"):
			return frappe.db.get_value(
				"Rental Unit", {"unit_name": row["unit_name"], "rental_item": row["rental_item"]}
			)
	return None


def _values(doctype: str, row: dict) -> tuple[dict, dict]:
	"""Split a row into field values and external identifiers. Empty cells leave a field unchanged."""
	values, ids = {}, {}
	for key, value in row.items():
		if key == "name" or value == "":
			continue
		if key.startswith(ID_PREFIX):
			ids[key[len(ID_PREFIX) :].strip()] = value
		else:
			values[key] = value
	return values, ids


def import_row(doctype: str, row: dict) -> tuple[str, str]:
	"""Create or update one record. Returns (name, "created" | "updated" | "unchanged")."""
	if row.get("rental_item"):
		row = {**row, "rental_item": _resolve_item(row["rental_item"])}
	values, ids = _values(doctype, row)
	name = find_existing(doctype, row)
	if name:
		doc = frappe.get_doc(doctype, name)
		if not frappe.has_permission(doctype, "write", doc):
			frappe.throw(_("Not permitted"), frappe.PermissionError)
	else:
		if not frappe.has_permission(doctype, "create"):
			frappe.throw(_("Not permitted"), frappe.PermissionError)
		doc = frappe.new_doc(doctype)
		if doctype == "Customer":
			values.setdefault("customer_type", "Individual")
			values.setdefault("customer_group", setup_ui._first_leaf("Customer Group"))
			values.setdefault("territory", setup_ui._first_leaf("Territory"))
	changed = False
	for key, value in values.items():
		if str(doc.get(key) if doc.get(key) is not None else "") != value:
			doc.set(key, value)
			changed = True
	for id_type, id_value in ids.items():
		existing = next((r for r in doc.get("external_ids") or [] if r.id_type == id_type), None)
		if existing and existing.id_value != id_value:
			existing.id_value = id_value
			changed = True
		elif not existing:
			doc.append("external_ids", {"id_type": id_type, "id_value": id_value})
			changed = True
	if not name:
		doc.insert()
		return doc.name, "created"
	if changed:
		doc.save()
		return doc.name, "updated"
	return doc.name, "unchanged"


def import_csv(doctype: str, content: str, dry_run: bool = False) -> dict:
	"""Import ``content`` into ``doctype``. With ``dry_run`` every change is rolled back (a preview)."""
	if doctype not in DOCTYPES:
		frappe.throw(_("{0} cannot be imported").format(doctype))
	rows = parse(content)
	check_columns(doctype, rows[0].keys() if rows else [])
	out = {"created": [], "updated": [], "unchanged": [], "errors": []}
	if dry_run:
		frappe.db.savepoint("rental_import_preview")
	for idx, row in enumerate(rows, start=2):  # row 1 is the header
		frappe.db.savepoint("rental_import")
		try:
			name, result = import_row(doctype, row)
			out[result].append(name)
		except Exception as e:
			frappe.db.rollback(save_point="rental_import")
			frappe.clear_messages()
			out["errors"].append({"row": idx, "error": frappe.utils.strip_html(str(e)) or type(e).__name__})
	if dry_run:
		frappe.db.rollback(save_point="rental_import_preview")
	return out


def template(doctype: str) -> str:
	"""A header-only CSV with the writable columns for ``doctype``."""
	if doctype not in DOCTYPES:
		frappe.throw(_("{0} cannot be imported").format(doctype))
	cols = list(setup_ui.SCREENS[doctype]["fields"])
	if doctype == "Rental Unit":
		cols.append(ID_PREFIX + "rfid")
	buf = io.StringIO()
	csv.writer(buf).writerow(cols)
	return buf.getvalue()

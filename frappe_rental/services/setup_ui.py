"""Setup screens for the staff app (T20): item types, items, units and customers.

One small, allowlisted read/write layer instead of exposing generic document APIs to the SPA. Every screen
names the doctype, the list columns and the fields the form may write. Writes go through ``Document.insert``
and ``Document.save``, so doctype permissions and controller validation apply unchanged.
"""

import frappe
from frappe import _
from frappe.utils import cint

SCREENS = {
	"Rental Type": {
		"title": "name",
		"list": ["name", "mode", "time_unit", "identification_mode", "requires_hold"],
		"fields": [
			"type_name",
			"mode",
			"time_unit",
			"identification_mode",
			"min_duration",
			"max_duration",
			"buffer_before",
			"buffer_after",
			"allow_quantity",
			"requires_hold",
			"requires_deposit",
			"requires_contract",
			"requires_checkin",
			"requires_return_inspection",
			"deposit_rule",
			"cancellation_policy",
			"tax_template",
		],
		"tables": {"custom_fields": ["applies_to", "label", "fieldname", "fieldtype", "options", "reqd"]},
		"search": ["name"],
	},
	"Rental Item": {
		"title": "item_name",
		"list": ["name", "item_name", "rental_type", "location", "rate_card", "is_published"],
		"fields": [
			"item_name",
			"rental_type",
			"location",
			"rate_card",
			"capacity_people",
			"is_published",
			"description",
		],
		"tables": {},
		"search": ["name", "item_name"],
		"custom_for": "Rental Item",
	},
	"Rental Unit": {
		"title": "unit_name",
		"list": ["name", "unit_name", "rental_item", "status", "location", "barcode"],
		"fields": [
			"unit_name",
			"rental_item",
			"status",
			"location",
			"barcode",
			"serial_no",
			"batch_no",
			"asset",
			"quantity_available",
		],
		"tables": {},
		"search": ["name", "unit_name", "barcode"],
		"custom_for": "Rental Unit",
	},
	"Rental Rate Card": {
		"title": "card_name",
		"list": ["name", "card_name", "currency", "enabled", "rounding_mode"],
		"fields": ["card_name", "currency", "enabled", "rounding_mode", "minimum_charge"],
		"tables": {
			"rates": [
				"time_unit",
				"rate",
				"min_units",
				"max_units",
				"priority",
				"valid_from",
				"valid_to",
				"weekday_mask",
				"season",
				"customer_group",
				"rental_unit",
			]
		},
		"search": ["name", "card_name"],
	},
	"Customer": {
		"title": "customer_name",
		"list": ["name", "customer_name", "customer_type", "customer_group", "territory"],
		"fields": ["customer_name", "customer_type", "customer_group", "territory"],
		"tables": {},
		"search": ["name", "customer_name"],
	},
}
LIST_FILTERS = {"rental_type", "rental_item", "location", "status", "mode", "customer_group"}
MAX_PAGE = 200


def _screen(doctype: str) -> dict:
	if doctype not in SCREENS:
		frappe.throw(_("{0} is not a setup screen").format(doctype))
	return SCREENS[doctype]


def _check(doctype: str, ptype: str, doc=None) -> None:
	if not frappe.has_permission(doctype, ptype, doc):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def get_records(
	doctype: str,
	search: str | None = None,
	filters: dict | None = None,
	start: int = 0,
	page_length: int = 50,
) -> dict:
	screen = _screen(doctype)
	_check(doctype, "read")
	where = []
	for key, value in (filters or {}).items():
		if key not in LIST_FILTERS or key not in screen["list"] + screen["fields"]:
			frappe.throw(_("Filter {0} is not allowed").format(key))
		if value not in (None, ""):
			where.append([doctype, key, "=", value])
	or_where = [[doctype, f, "like", f"%{search}%"] for f in screen["search"]] if search else None
	page_length = max(1, min(cint(page_length) or 50, MAX_PAGE))
	rows = frappe.get_list(
		doctype,
		fields=screen["list"],
		filters=where,
		or_filters=or_where,
		order_by="modified desc",
		start=cint(start),
		page_length=page_length,
	)
	total = len(
		frappe.get_list(doctype, filters=where, or_filters=or_where, pluck="name", limit_page_length=0)
	)
	return {"rows": rows, "total": total}


def custom_fields(doctype: str, rental_type: str | None) -> list[dict]:
	"""Custom fields a Rental Type adds to ``doctype``, shaped for the form renderer."""
	if not rental_type:
		return []
	return frappe.get_all(
		"Rental Type Custom Field",
		filters={"parent": rental_type, "parenttype": "Rental Type", "applies_to": doctype},
		fields=["label", "fieldname", "fieldtype", "options", "reqd"],
		order_by="idx asc",
	)


def _rental_type_of(doctype: str, data: dict) -> str | None:
	if doctype == "Rental Item":
		return data.get("rental_type")
	if doctype == "Rental Unit" and data.get("rental_item"):
		return frappe.db.get_value("Rental Item", data["rental_item"], "rental_type")
	return None


def get_record(doctype: str, name: str) -> dict:
	screen = _screen(doctype)
	doc = frappe.get_doc(doctype, name)
	_check(doctype, "read", doc)
	out = {"name": doc.name, "title": doc.get(screen["title"]) or doc.name}
	out.update({f: doc.get(f) for f in screen["fields"]})
	for table, cols in screen["tables"].items():
		out[table] = [{c: row.get(c) for c in cols} for row in doc.get(table)]
	extra = (
		custom_fields(screen.get("custom_for"), _rental_type_of(doctype, out))
		if screen.get("custom_for")
		else []
	)
	out["custom"] = {f.fieldname: doc.get(f.fieldname) for f in extra}
	out["custom_meta"] = extra
	out["can_write"] = bool(frappe.has_permission(doctype, "write", doc))
	if doctype == "Rental Item":
		out["units"] = frappe.get_list(
			"Rental Unit",
			filters={"rental_item": doc.name},
			fields=["name", "unit_name", "status"],
			limit_page_length=0,
		)
	if doctype == "Rental Type":
		out["items"] = frappe.get_list(
			"Rental Item",
			filters={"rental_type": doc.name},
			fields=["name", "item_name"],
			limit_page_length=0,
		)
	return out


def save_record(doctype: str, data: dict, name: str | None = None) -> str:
	"""Create (no name) or update a record from the form. Unknown keys are rejected, not ignored."""
	screen = _screen(doctype)
	extra = {
		f.fieldname
		for f in (
			custom_fields(screen.get("custom_for"), _rental_type_of(doctype, data))
			if screen.get("custom_for")
			else []
		)
	}
	allowed = set(screen["fields"]) | set(screen["tables"]) | {"custom"}
	unknown = set(data) - allowed
	if unknown:
		frappe.throw(_("Fields not allowed: {0}").format(", ".join(sorted(unknown))))
	values = {k: v for k, v in data.items() if k in screen["fields"]}
	for key, value in (data.get("custom") or {}).items():
		if key not in extra:
			frappe.throw(_("Field {0} is not defined for this item type").format(key))
		values[key] = value
	for table, cols in screen["tables"].items():
		if table in data:
			values[table] = [{c: row.get(c) for c in cols if c in row} for row in data[table] or []]
	if name:
		doc = frappe.get_doc(doctype, name)
		_check(doctype, "write", doc)
		doc.update(values)
		doc.save()
	else:
		_check(doctype, "create")
		if doctype == "Customer":
			values.setdefault("customer_type", "Individual")
			values.setdefault("customer_group", _first_leaf("Customer Group"))
			values.setdefault("territory", _first_leaf("Territory"))
		doc = frappe.get_doc({"doctype": doctype, **values})
		doc.insert()
	return doc.name


def _first_leaf(doctype: str) -> str | None:
	return frappe.db.get_value(doctype, {"is_group": 0}, "name", order_by="lft asc")


def options() -> dict:
	"""Choices for selects on the setup forms."""

	def names(dt, **filters):
		return (
			frappe.get_list(dt, filters=filters, pluck="name", order_by="name asc", limit_page_length=0)
			if frappe.has_permission(dt, "read")
			else []
		)

	def select(dt, field):
		return [o for o in (frappe.get_meta(dt).get_field(field).options or "").split("\n") if o]

	return {
		"rental_types": names("Rental Type"),
		"locations": names("Rental Location"),
		"rate_cards": names("Rental Rate Card"),
		"deposit_rules": names("Rental Deposit Rule"),
		"cancellation_policies": names("Rental Cancellation Policy"),
		"customer_groups": names("Customer Group", is_group=0),
		"territories": names("Territory", is_group=0),
		"modes": select("Rental Type", "mode"),
		"time_units": select("Rental Type", "time_unit"),
		"rounding_modes": select("Rental Rate Card", "rounding_mode"),
		"identification_modes": select("Rental Type", "identification_mode"),
		"unit_statuses": select("Rental Unit", "status"),
		"field_types": select("Rental Type Custom Field", "fieldtype"),
		"applies_to": select("Rental Type Custom Field", "applies_to"),
		"customer_types": select("Customer", "customer_type"),
	}

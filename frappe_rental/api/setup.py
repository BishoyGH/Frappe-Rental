import json

import frappe
from frappe import _

from frappe_rental.services import rental_type as rental_type_service
from frappe_rental.services import setup_ui


@frappe.whitelist()
def install_presets() -> list[str]:
	"""Install the bundled Rental Type presets (button on the Rental Type list)."""
	if not frappe.has_permission("Rental Type", "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return rental_type_service.install_presets()


def _obj(value, label: str) -> dict:
	data = json.loads(value) if isinstance(value, str) and value else (value or {})
	if not isinstance(data, dict):
		frappe.throw(_("{0} must be an object").format(label))
	return data


@frappe.whitelist()
def get_records(
	doctype: str,
	search: str | None = None,
	filters: str | dict | None = None,
	start: int = 0,
	page_length: int = 50,
) -> dict:
	"""List rows for a setup screen (Rental Type, Rental Item, Rental Unit, Customer)."""
	return setup_ui.get_records(doctype, search, _obj(filters, _("Filters")), start, page_length)


@frappe.whitelist()
def get_record(doctype: str, name: str) -> dict:
	"""One record for a setup form, with the custom fields its item type adds."""
	return setup_ui.get_record(doctype, name)


@frappe.whitelist(methods=["POST"])
def save_record(doctype: str, data: str | dict, name: str | None = None) -> dict:
	"""Create or update a setup record; only the screen's fields are accepted."""
	return {"name": setup_ui.save_record(doctype, _obj(data, _("Data")), name or None)}


@frappe.whitelist()
def form_options() -> dict:
	"""Select choices for the setup forms."""
	if not frappe.has_permission("Rental Type", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return setup_ui.options()


@frappe.whitelist()
def type_fields(doctype: str, rental_type: str | None = None, rental_item: str | None = None) -> list[dict]:
	"""Custom fields an item type adds to Rental Item or Rental Unit (for a new record's form)."""
	if doctype not in ("Rental Item", "Rental Unit") or not frappe.has_permission("Rental Type", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if rental_item and not rental_type:
		if not frappe.has_permission("Rental Item", "read", doc=rental_item):
			frappe.throw(_("Not permitted"), frappe.PermissionError)
		rental_type = frappe.db.get_value("Rental Item", rental_item, "rental_type")
	return setup_ui.custom_fields(doctype, rental_type)

"""Shared test helpers (T03). Fixtures are built in code, idempotently, with no reliance on demo data.

Factories for Rental Type, Unit and Booking are added by the tasks that create those doctypes (T06 onward).
Anything that differs between ERPNext v15 and v16 must go through ``frappe_rental.compat``.
"""

import frappe
from frappe.utils import random_string

from frappe_rental.compat.erpnext import ensure_setup_complete


def make_company() -> str:
	"""Return the site's default company, completing ERPNext setup first if the site is bare."""
	return ensure_setup_complete()


def make_customer(name: str | None = None) -> str:
	"""Return a Customer, creating it if needed. Without a name a unique one is generated."""
	ensure_setup_complete()
	name = name or f"Test Customer {random_string(6)}"
	if frappe.db.exists("Customer", name):
		return name
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name,
			"customer_type": "Individual",
			"customer_group": _first("Customer Group", {"is_group": 0}),
			"territory": _first("Territory", {"is_group": 0}),
		}
	)
	doc.insert()
	return doc.name


def make_item(item_code: str | None = None, is_stock_item: int = 0, rate: float = 0) -> str:
	"""Return an Item (non-stock service by default)."""
	ensure_setup_complete()
	item_code = item_code or f"TEST-ITEM-{random_string(6)}"
	if frappe.db.exists("Item", item_code):
		return item_code
	doc = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_name": item_code,
			"item_group": _first("Item Group", {"is_group": 0}),
			"stock_uom": _first("UOM", {}),
			"is_stock_item": is_stock_item,
			"standard_rate": rate,
		}
	)
	doc.insert()
	return doc.name


def make_fixture_set() -> dict:
	"""A basic fixture set: company, customer and item."""
	return {"company": make_company(), "customer": make_customer(), "item": make_item()}


def _first(doctype: str, filters: dict) -> str:
	name = frappe.db.get_value(doctype, filters, "name")
	if not name:
		raise frappe.ValidationError(f"No {doctype} found; is ERPNext installed and set up?")
	return name

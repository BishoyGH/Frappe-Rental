"""Rental Item logic (T07): keep the linked ERPNext Item in sync, both ways.

Rental Item -> Item on every save (create if missing). Item -> Rental Item for the shared fields
(name, description, image) when the Item is edited directly in ERPNext. A flag on the Item stops
the two hooks from calling each other.
"""

import frappe
from frappe import _

from frappe_rental.services.setup import ITEM_GROUP

SHARED_FIELDS = ("item_name", "description", "image")
SYNC_FLAG = "from_rental_item"


def income_account(rental_type: str | None) -> str | None:
	"""Rental Type's income account, else the Rental Settings default."""
	account = rental_type and frappe.db.get_value("Rental Type", rental_type, "income_account")
	return account or frappe.db.get_single_value("Rental Settings", "rental_income_account")


def sync_item(doc) -> str:
	"""Create or update the Item for a Rental Item. Idempotent; returns the item code."""
	code = doc.item_code or doc.name
	exists = frappe.db.exists("Item", code)
	item = frappe.get_doc("Item", code) if exists else frappe.new_doc("Item")
	if not exists:
		item.update(
			{
				"item_code": code,
				"item_group": _item_group(),
				"stock_uom": _stock_uom(),
				"is_stock_item": 0,
				"is_sales_item": 1,
				"include_item_in_manufacturing": 0,
			}
		)
	for field in SHARED_FIELDS:
		item.set(field, doc.get(field))
	if item.meta.has_field("rental_item"):
		item.rental_item = doc.name
	_set_income_account(item, income_account(doc.rental_type))
	item.flags[SYNC_FLAG] = True
	item.save(ignore_permissions=True)  # Item is owned by the Rental Item; the user already passed its check
	if doc.item_code != item.name:
		doc.db_set("item_code", item.name, update_modified=False)
	return item.name


def sync_from_item(item) -> None:
	"""Copy shared fields from an Item edited in ERPNext back to its Rental Item."""
	if item.flags.get(SYNC_FLAG):
		return
	name = frappe.db.get_value("Rental Item", {"item_code": item.name}, "name")
	if not name:
		return
	current = frappe.db.get_value("Rental Item", name, SHARED_FIELDS, as_dict=True)
	changed = {f: item.get(f) for f in SHARED_FIELDS if (current.get(f) or None) != (item.get(f) or None)}
	if changed:
		frappe.db.set_value("Rental Item", name, changed)


def _set_income_account(item, account: str | None) -> None:
	company = frappe.db.get_single_value("Rental Settings", "default_company")
	if not (company and account):
		return
	if frappe.db.get_value("Account", account, "company") != company:
		frappe.throw(_("Income account {0} does not belong to company {1}").format(account, company))
	for row in item.get("item_defaults") or []:
		if row.company == company:
			row.income_account = account
			return
	item.append("item_defaults", {"company": company, "income_account": account})


def _item_group() -> str:
	if frappe.db.exists("Item Group", ITEM_GROUP):
		return ITEM_GROUP
	return frappe.db.get_value("Item Group", {"is_group": 0}, "name") or frappe.db.get_value(
		"Item Group", {"parent_item_group": ["is", "not set"]}, "name"
	)


def _stock_uom() -> str:
	return (
		frappe.db.get_single_value("Stock Settings", "stock_uom")
		or (frappe.db.exists("UOM", "Nos") and "Nos")
		or frappe.db.get_value("UOM", {}, "name")
	)


def item_on_update(doc, method=None) -> None:
	"""doc_events hook for Item."""
	sync_from_item(doc)

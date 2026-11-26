"""ERPNext-specific shims.

Add helpers here before any task reads ERPNext fields or behaviour that differ between v15 and v16.
"""

import frappe
from frappe.utils import now_datetime


def ensure_setup_complete() -> str:
	"""Run the ERPNext setup wizard on a bare site and return the default company.

	Versions: v15 ships a ``before_tests`` hook that completes setup before ``run-tests``; v16 does not,
	so a fresh bench site has no Company, Warehouse Types, Customer Groups, etc. Detected by feature
	(is there a Company?), not by version number.
	Removal: when v15 support is dropped and v16 gains its own equivalent, or both always run setup.
	"""
	company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
	if company:
		return company

	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	year = now_datetime().year
	setup_complete(
		{
			"currency": "USD",
			"full_name": "Test User",
			"company_name": "Rental Test Co",
			"timezone": "America/New_York",
			"company_abbr": "RTC",
			"industry": "Manufacturing",
			"country": "United States",
			"fy_start_date": f"{year}-01-01",
			"fy_end_date": f"{year}-12-31",
			"language": "english",
			"company_tagline": "Testing",
			"email": "test@example.com",
			"password": "test",
			"chart_of_accounts": "Standard",
		}
	)
	frappe.clear_cache()
	return frappe.db.get_value("Company", {}, "name", order_by="creation asc")


def template_taxes(template: str | None) -> list[dict]:
	"""Rows of a Sales Taxes and Charges Template, ready for a transaction's `taxes` table.

	Versions: v15 and v16 both expose `get_taxes_and_charges` in `erpnext.controllers.accounts_controller`
	with the same signature. Feature-detected so a move only needs this shim changed.
	Removal: keep while the function lives in different places or signatures across supported majors.
	"""
	if not template:
		return []
	from erpnext.controllers import accounts_controller

	getter = getattr(accounts_controller, "get_taxes_and_charges", None)
	if getter:
		return getter("Sales Taxes and Charges Template", template) or []
	doc = frappe.get_doc("Sales Taxes and Charges Template", template)
	return [
		{
			k: v
			for k, v in row.as_dict().items()
			if k not in ("name", "parent", "parenttype", "parentfield", "idx")
		}
		for row in doc.taxes
	]


def make_sales_invoice_from_order(sales_order: str):
	"""Map a submitted Sales Order to a new, unsaved Sales Invoice.

	Versions: `erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice` on v15 and v16.
	Removal: when its import path or signature differs between supported majors, branch here.
	"""
	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

	return make_sales_invoice(sales_order)


def make_credit_note(sales_invoice: str):
	"""Unsaved return (credit note) for a submitted Sales Invoice.

	Versions: `erpnext.accounts.doctype.sales_invoice.sales_invoice.make_sales_return` on v15 and v16.
	Removal: as above.
	"""
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

	return make_sales_return(sales_invoice)


def create_dimension_fields(dimension: str) -> None:
	"""Add an Accounting Dimension's fields to every accounting doctype now, not in a background job.

	Versions: v15 and v16 enqueue `make_dimension_in_accounting_doctypes` outside tests, so a site with
	no worker (fresh install, CI) misses the columns and v16's budget check then fails on submit.
	Calling the same public function inline is idempotent (it skips existing fields).
	Removal: when ERPNext creates dimension fields synchronously on both supported majors.
	"""
	from erpnext.accounts.doctype.accounting_dimension import accounting_dimension

	accounting_dimension.make_dimension_in_accounting_doctypes(
		doc=frappe.get_doc("Accounting Dimension", dimension)
	)


def enable_serial_numbers() -> None:
	"""Allow serialised items.

	ERPNext v16 adds Stock Settings `enable_serial_and_batch_no_for_item`, off by default, which blocks
	`has_serial_no`; v15 has no such switch. Feature-detected; remove when v15 support ends and set the
	field directly.
	"""
	field = "enable_serial_and_batch_no_for_item"
	if frappe.get_meta("Stock Settings").has_field(field) and not frappe.db.get_single_value(
		"Stock Settings", field
	):
		frappe.db.set_single_value("Stock Settings", field, 1)


def make_refund_entry(credit_note: str, amount: float):
	"""Unsaved Payment Entry (Pay) refunding `amount` of a submitted credit note to the customer.

	Versions: `erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry` on v15 and v16;
	for a return invoice it builds a "Pay" entry with the credit note as reference. Removal: keep while
	the function and its return-invoice behaviour are unchanged on every supported major.
	"""
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	pe = get_payment_entry("Sales Invoice", credit_note)
	pe.paid_amount = pe.received_amount = amount
	for ref in pe.references:
		ref.allocated_amount = -amount if ref.allocated_amount < 0 else amount
	if hasattr(pe, "set_amounts"):
		pe.set_amounts()
	return pe


def stock_transfer(company: str, rows: list[dict], reference: dict | None = None) -> str:
	"""Submit a Material Transfer Stock Entry. Each row: item_code, qty, s_warehouse, t_warehouse,
	optional serial_no (newline separated) and batch_no.

	Versions: v15 and v16 both move serials and batches through Serial and Batch Bundles. The
	`use_serial_batch_fields` row flag (v15.x and v16) lets plain `serial_no` / `batch_no` values build
	the bundle for us; on a build without the flag the plain fields are read directly.
	Feature-detected per field. Removal: when the oldest supported major always has the flag.
	"""
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Transfer"
	se.purpose = "Material Transfer"
	se.company = company
	se.update(reference or {})
	has_flag = frappe.get_meta("Stock Entry Detail").has_field("use_serial_batch_fields")
	for row in rows:
		item = dict(row)
		if has_flag and (item.get("serial_no") or item.get("batch_no")):
			item["use_serial_batch_fields"] = 1
		se.append("items", item)
	se.flags.ignore_permissions = True  # stock follows a permitted handover
	se.insert()
	se.submit()
	return se.name


def move_asset(asset: str, company: str, target_location: str, reference: dict | None = None) -> str:
	"""Submit an Asset Movement (Transfer) of one asset to an ERPNext Location.

	Versions: Asset Movement with an `assets` table (asset, source_location, target_location) and
	purpose "Transfer" on v15 and v16. Removal: keep while the shape is the same on every major.
	"""
	source = frappe.db.get_value("Asset", asset, "location")
	am = frappe.new_doc("Asset Movement")
	am.update(
		{"company": company, "purpose": "Transfer", "transaction_date": now_datetime(), **(reference or {})}
	)
	am.append("assets", {"asset": asset, "source_location": source, "target_location": target_location})
	am.flags.ignore_permissions = True  # asset follows a permitted handover
	am.insert()
	am.submit()
	return am.name


def make_asset_repair(asset: str, company: str, description: str, failure_date) -> str:
	"""Draft Asset Repair for a damaged asset. Returns its name.

	Versions: Asset Repair with asset, company, failure_date and description on v15 and v16; repair
	cost and stock items are filled in by the user before submitting. Removal: keep while the fields
	are unchanged on every supported major.
	"""
	repair = frappe.new_doc("Asset Repair")
	repair.update(
		{"asset": asset, "company": company, "failure_date": failure_date, "description": description}
	)
	repair.flags.ignore_permissions = True  # drafted from a permitted damage report
	repair.flags.ignore_mandatory = True  # the user completes costs before submitting
	repair.insert()
	return repair.name


def make_signed_contract(customer: str, start_date, end_date, terms_html: str, signee: str, signed_on) -> str:
	"""Create the ERPNext Contract mirroring a signed Rental Contract. Returns its name.

	Versions: Contract (party_type, party_name, start_date, end_date, contract_terms, is_signed, signee,
	signed_on) on v15 and v16; it is submitted when the doctype is submittable. Feature-detected by
	meta. Removal: keep while the fields are unchanged on every supported major.
	"""
	doc = frappe.new_doc("Contract")
	doc.update(
		{
			"party_type": "Customer",
			"party_name": customer,
			"start_date": start_date,
			"end_date": end_date,
			"contract_terms": terms_html,
			"is_signed": 1,
			"signee": signee,
			"signed_on": signed_on,
		}
	)
	doc.flags.ignore_permissions = True  # mirror of a permitted Rental Contract signature
	doc.insert()
	if doc.meta.is_submittable:
		doc.submit()
	return doc.name

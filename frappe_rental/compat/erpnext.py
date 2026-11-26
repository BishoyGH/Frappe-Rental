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

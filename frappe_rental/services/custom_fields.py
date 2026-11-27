"""Custom fields this app adds to ERPNext doctypes (T16). Created on install and migrate; idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def _link(fieldname, label, options, insert_after, **kw):
	return {
		"fieldname": fieldname,
		"label": label,
		"fieldtype": "Link",
		"options": options,
		"insert_after": insert_after,
		"read_only": 1,
		"no_copy": 1,
		"module": "Rental",
		**kw,
	}


def _line_fields(after):
	return [
		_link("rental_unit", "Rental Unit", "Rental Unit", after, allow_on_submit=1),
		{
			"fieldname": "rental_booking_line",
			"label": "Rental Booking Line",
			"fieldtype": "Data",
			"insert_after": "rental_unit",
			"read_only": 1,
			"no_copy": 1,
			"hidden": 1,
			"module": "Rental",
		},
	]


CUSTOM_FIELDS = {
	"Sales Order": [
		_link("rental_booking", "Rental Booking", "Rental Booking", "customer_name", in_standard_filter=1)
	],
	"Sales Invoice": [
		_link("rental_booking", "Rental Booking", "Rental Booking", "customer_name", in_standard_filter=1),
		{
			"fieldname": "rental_billing_row",
			"label": "Rental Billing Row",
			"fieldtype": "Data",
			"insert_after": "rental_booking",
			"read_only": 1,
			"no_copy": 1,
			"hidden": 1,
			"search_index": 1,
			"module": "Rental",
		},
	],
	"Sales Order Item": _line_fields("item_name"),
	"Sales Invoice Item": [
		*_line_fields("item_name"),
		# T50: consolidated invoices reference the booking and billing row per item
		_link("rental_booking", "Rental Booking", "Rental Booking", "rental_booking_line"),
		{
			"fieldname": "rental_billing_row",
			"label": "Rental Billing Row",
			"fieldtype": "Data",
			"insert_after": "rental_booking",
			"read_only": 1,
			"no_copy": 1,
			"hidden": 1,
			"search_index": 1,
			"module": "Rental",
		},
	],
	"Customer": [
		{
			"fieldname": "rental_consolidate_invoices",
			"label": "Consolidate Rental Invoices",
			"description": "One invoice per billing run for all of this customer's rentals",
			"fieldtype": "Check",
			"insert_after": "customer_group",
			"module": "Rental",
		}
	],
	"Journal Entry": [_link("rental_deposit", "Rental Deposit", "Rental Deposit", "voucher_type")],
	"Serial No": [
		_link("rental_booking", "Rented On", "Rental Booking", "warehouse"),
		_link("rental_customer", "Rented To", "Customer", "rental_booking"),
	],
	"Stock Entry": [_link("rental_handover", "Rental Handover", "Rental Handover", "stock_entry_type")],
	"Asset Movement": [_link("rental_handover", "Rental Handover", "Rental Handover", "purpose")],
	"Asset": [_link("rental_unit", "Rental Unit", "Rental Unit", "item_name")],
	"Item": [_link("rental_item", "Rental Item", "Rental Item", "item_name")],
	"Project": [_link("rental_booking", "Rental Booking", "Rental Booking", "customer", search_index=1)],
}


def install() -> None:
	try:
		create_custom_fields(CUSTOM_FIELDS, update=True)
	except frappe.ValidationError:
		# Frappe v16 on Postgres re-validates a standard field whose JSON `link_filters` the driver
		# returns already decoded, and rejects it. Remove when Frappe fixes it. Retry per doctype
		# without the re-validation, then rebuild the tables (covered by the Postgres CI legs).
		frappe.db.rollback()
		for doctype, fields in CUSTOM_FIELDS.items():
			for f in fields:
				name = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": f["fieldname"]})
				doc = frappe.get_doc({"doctype": "Custom Field", "dt": doctype, **f})
				if name:
					doc.name = name
					doc.flags.in_import = True
					doc.db_update()
				else:
					doc.flags.in_import = True
					doc.set_new_name()
					doc.db_insert()
			frappe.clear_cache(doctype=doctype)
			frappe.db.updatedb(doctype)

"""Custom fields this app adds to ERPNext doctypes (T16). Created on install and migrate; idempotent."""

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
	"Sales Invoice Item": _line_fields("item_name"),
	"Asset": [_link("rental_unit", "Rental Unit", "Rental Unit", "item_name")],
	"Item": [_link("rental_item", "Rental Item", "Rental Item", "item_name")],
}


def install() -> None:
	create_custom_fields(CUSTOM_FIELDS, update=True)

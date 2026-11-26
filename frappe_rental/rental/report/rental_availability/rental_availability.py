"""Rental Availability (T30). Logic in services.reports."""

import frappe
from frappe import _


def execute(filters=None):
	f = frappe._dict(filters or {})
	if not (f.from_datetime and f.to_datetime):
		return [], []
	from frappe_rental.services import search

	rows = search.search(f.from_datetime, f.to_datetime, rental_type=f.rental_type, location=f.location)
	columns = [
		{
			"fieldname": "rental_unit",
			"label": _("Unit"),
			"fieldtype": "Link",
			"options": "Rental Unit",
			"width": 180,
		},
		{
			"fieldname": "rental_item",
			"label": _("Item"),
			"fieldtype": "Link",
			"options": "Rental Item",
			"width": 180,
		},
		{
			"fieldname": "location",
			"label": _("Location"),
			"fieldtype": "Link",
			"options": "Rental Location",
			"width": 140,
		},
		{"fieldname": "price", "label": _("Price"), "fieldtype": "Currency", "width": 120},
	]
	return columns, rows

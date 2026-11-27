"""Rental Overdue Returns (T30). Logic in services.reports."""

from frappe import _

from frappe_rental.services import reports


def execute(filters=None):
	rows = reports.overdue_returns()
	columns = [
		{
			"fieldname": "name",
			"label": _("Booking"),
			"fieldtype": "Link",
			"options": "Rental Booking",
			"width": 160,
		},
		{
			"fieldname": "customer",
			"label": _("Customer"),
			"fieldtype": "Link",
			"options": "Customer",
			"width": 180,
		},
		{
			"fieldname": "rental_type",
			"label": _("Type"),
			"fieldtype": "Link",
			"options": "Rental Type",
			"width": 140,
		},
		{"fieldname": "to_datetime", "label": _("Due back"), "fieldtype": "Datetime", "width": 160},
		{"fieldname": "hours_overdue", "label": _("Hours overdue"), "fieldtype": "Float", "width": 120},
	]
	return columns, rows

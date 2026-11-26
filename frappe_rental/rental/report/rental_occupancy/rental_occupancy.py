"""Rental Occupancy (T30). Logic in services.reports."""

import frappe
from frappe import _
from frappe.utils import add_days

from frappe_rental.services import reports


def execute(filters=None):
	f = frappe._dict(filters or {})
	rows = reports.occupancy(
		f"{f.from_date} 00:00:00", f"{add_days(f.to_date, 1)} 00:00:00", f.location, f.rental_type
	)
	columns = [
		{
			"fieldname": "name",
			"label": _("Unit"),
			"fieldtype": "Link",
			"options": "Rental Unit",
			"width": 180,
		},
		{
			"fieldname": "rental_type",
			"label": _("Type"),
			"fieldtype": "Link",
			"options": "Rental Type",
			"width": 140,
		},
		{
			"fieldname": "location",
			"label": _("Location"),
			"fieldtype": "Link",
			"options": "Rental Location",
			"width": 140,
		},
		{"fieldname": "booked_hours", "label": _("Booked hours"), "fieldtype": "Float", "width": 120},
		{"fieldname": "period_hours", "label": _("Hours in period"), "fieldtype": "Float", "width": 120},
		{"fieldname": "occupancy_pct", "label": _("Utilisation %"), "fieldtype": "Percent", "width": 120},
	]
	return columns, rows

"""Rental Asset ROI (T30). Logic in services.reports."""

import frappe
from frappe import _

from frappe_rental.services import reports


def execute(filters=None):
	f = frappe._dict(filters or {})
	columns = [
		{
			"fieldname": "rental_unit",
			"label": _("Unit"),
			"fieldtype": "Link",
			"options": "Rental Unit",
			"width": 180,
		},
		{"fieldname": "asset", "label": _("Asset"), "fieldtype": "Link", "options": "Asset", "width": 160},
		{"fieldname": "cost", "label": _("Asset cost"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "revenue", "label": _("Rental revenue"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "roi_pct", "label": _("ROI %"), "fieldtype": "Percent", "width": 100},
	]
	return columns, reports.asset_roi(f.company)

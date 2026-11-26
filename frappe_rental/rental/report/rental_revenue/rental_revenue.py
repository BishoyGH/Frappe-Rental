"""Rental Revenue (T30). Logic in services.reports."""

import frappe
from frappe import _

from frappe_rental.services import reports


def execute(filters=None):
	f = frappe._dict(filters or {})
	rows = reports.revenue(f.from_date, f.to_date, f.company, f.group_by or "rental_type")
	columns = [
		{"fieldname": "group", "label": _("Group"), "fieldtype": "Data", "width": 220},
		{"fieldname": "revenue", "label": _("Revenue"), "fieldtype": "Currency", "width": 160},
		{"fieldname": "invoices", "label": _("Invoices"), "fieldtype": "Int", "width": 100},
	]
	chart = {
		"data": {"labels": [r.group for r in rows], "datasets": [{"values": [r.revenue for r in rows]}]},
		"type": "bar",
	}
	return columns, rows, None, chart

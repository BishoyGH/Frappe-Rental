"""Rental Unit History (T30). Logic in services.reports."""

import frappe
from frappe import _

from frappe_rental.services import reports


def execute(filters=None):
	f = frappe._dict(filters or {})
	if not f.rental_unit:
		return [], []
	if not frappe.has_permission("Rental Unit", "read", f.rental_unit):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	columns = [
		{"fieldname": "at", "label": _("When"), "fieldtype": "Datetime", "width": 160},
		{"fieldname": "kind", "label": _("What"), "fieldtype": "Data", "width": 110},
		{"fieldname": "reference", "label": _("Document"), "fieldtype": "Data", "width": 180},
		{"fieldname": "detail", "label": _("Detail"), "fieldtype": "Data", "width": 300},
	]
	return columns, reports.unit_history(f.rental_unit)

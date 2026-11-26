"""Dashboard API (T30): KPI cards for the staff app. Figures come from services.reports."""

import frappe
from frappe import _

from frappe_rental.services import reports


@frappe.whitelist(methods=["GET", "POST"])
def kpis(company: str | None = None) -> dict:
	if not frappe.has_permission("Rental Booking", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if company and not frappe.has_permission("Company", "read", company):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return reports.kpis(company)


@frappe.whitelist(methods=["GET", "POST"])
def revenue(
	from_date: str, to_date: str, group_by: str = "rental_type", company: str | None = None
) -> list[dict]:
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return reports.revenue(from_date, to_date, company, group_by)

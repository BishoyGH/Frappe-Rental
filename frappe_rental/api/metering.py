"""Metered usage API (T49): post a reading (devices, staff app) and read the usage summary."""

import frappe
from frappe import _

from frappe_rental.services import metering


@frappe.whitelist(methods=["POST"])
def add_reading(booking: str, unit: str, reading: float, read_on: str | None = None) -> dict:
	if not frappe.has_permission("Rental Meter Reading", "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.has_permission("Rental Booking", "read", booking):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	name = metering.record(booking, unit, reading, "API", read_on)
	return {"name": name, **metering.summary(booking)}


@frappe.whitelist()
def summary(booking: str) -> dict:
	if not frappe.has_permission("Rental Booking", "read", booking):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return metering.summary(booking)

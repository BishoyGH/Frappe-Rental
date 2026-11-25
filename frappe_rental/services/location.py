"""Rental Location business logic (T05)."""

import zoneinfo

import frappe
from frappe import _


def validate_timezone(tz: str | None) -> None:
	if tz and tz not in zoneinfo.available_timezones():
		frappe.throw(_("Unknown timezone: {0}").format(tz))


def ensure_cost_center(location) -> str | None:
	"""Create a Cost Center named after the location under the company's root cost center. Idempotent."""
	if location.cost_center:
		return location.cost_center
	abbr = frappe.get_cached_value("Company", location.company, "abbr")
	name = f"{location.location_name} - {abbr}"
	if not frappe.db.exists("Cost Center", name):
		parent = frappe.db.get_value(
			"Cost Center",
			{"company": location.company, "is_group": 1, "parent_cost_center": ["is", "not set"]},
			"name",
		)
		if not parent:
			return None
		frappe.get_doc(
			{
				"doctype": "Cost Center",
				"cost_center_name": location.location_name,
				"company": location.company,
				"parent_cost_center": parent,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)  # system-created accounting record, see test_location
	location.db_set("cost_center", name)
	return name

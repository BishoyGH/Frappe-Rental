"""Composite indexes for the hot queries (T55). Applied on migrate by each doctype's `on_doctype_update`.

`frappe.db.add_index` is public on v15 and v16 (MariaDB and Postgres) and does nothing when the index
exists, so migrate is idempotent. Single-column indexes stay as `search_index` in the doctype JSON.
"""

import frappe

INDEXES = {
	# availability: overlapping_rows filters unit + window; release() deletes by source
	"Rental Availability Cache": [
		["rental_unit", "busy_from", "busy_to"],
		["source_doctype", "source_name"],
	],
	# invoicing job: Planned rows due by date; per-booking lookups
	"Rental Billing Schedule": [["status", "invoice_date"], ["parent", "status"]],
	# pending events per booking, leftovers by date, idempotency by source
	"Rental Billable Event": [
		["rental_booking", "status"],
		["status", "event_date"],
		["source_doctype", "source_name", "event_type"],
	],
	# calendars, lists, reports
	"Rental Booking": [["from_datetime", "to_datetime"], ["customer", "docstatus"], ["status"]],
	"Rental Booking Line": [["rental_unit", "parent"]],
	"Rental Meter Reading": [["rental_booking", "rental_unit", "read_on"]],
	"Rental Housekeeping Task": [["status", "due_by"], ["rental_unit", "status"]],
	"Rental Contract Visit": [["status", "planned_date"]],
}


def apply(doctype: str) -> None:
	for fields in INDEXES.get(doctype, []):
		frappe.db.add_index(doctype, fields)

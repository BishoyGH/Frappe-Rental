"""Load test for T55: seed N busy windows and time the hot paths.

Run on a throwaway site (it writes data and rolls back at the end):

    bench --site rental.localhost execute frappe_rental.perf.load.run --kwargs "{'bookings': 100000}"

Seeding writes Rental Availability Cache rows directly (the shape every booking leaves behind), spread
over `units` units and two years, so the availability and search queries see a 100k-booking table
without running 100k booking submits. Prints p50/p95 in milliseconds per measured call.
"""

import random
import statistics
import time
from datetime import datetime, timedelta

import frappe
from frappe.utils import random_string

from frappe_rental.services import availability, search


def _timed(fn, n):
	samples = []
	for _ in range(n):
		t = time.perf_counter()
		fn()
		samples.append((time.perf_counter() - t) * 1000)
	samples.sort()
	return {
		"p50": round(statistics.median(samples), 1),
		"p95": round(samples[int(len(samples) * 0.95) - 1], 1),
	}


def seed(bookings: int, units: list[str], start: datetime) -> None:
	rows, now = [], datetime.now()
	for i in range(bookings):
		unit = units[i % len(units)]
		f = start + timedelta(hours=random.randint(0, 2 * 365 * 24))
		rows.append(
			(
				frappe.generate_hash(length=12),
				now,
				now,
				"Administrator",
				"Administrator",
				unit,
				f,
				f + timedelta(hours=random.randint(2, 72)),
				1,
				"Rental Booking",
				f"PERF-{i}",
			)
		)
	fields = [
		"name",
		"creation",
		"modified",
		"owner",
		"modified_by",
		"rental_unit",
		"busy_from",
		"busy_to",
		"qty",
		"source_doctype",
		"source_name",
	]
	frappe.db.bulk_insert(availability.CACHE, fields, rows, chunk_size=5000)


def run(bookings: int = 100000, units: int = 500, samples: int = 200, rental_type: str | None = None):
	rental_type = rental_type or frappe.db.get_value("Rental Type", {}, "name")
	card = frappe.db.get_value("Rental Rate Card", {}, "name")
	item = frappe.get_doc(
		{
			"doctype": "Rental Item",
			"item_name": f"PERF {random_string(6)}",
			"rental_type": rental_type,
			"rate_card": card,
		}
	).insert(ignore_permissions=True)
	names = [
		frappe.get_doc(
			{"doctype": "Rental Unit", "unit_name": f"PERF {i} {random_string(4)}", "rental_item": item.name}
		)
		.insert(ignore_permissions=True)
		.name
		for i in range(units)
	]
	start = datetime(2026, 1, 1)
	t = time.perf_counter()
	seed(bookings, names, start)
	seeded = round(time.perf_counter() - t, 1)

	def one_check():
		f = start + timedelta(hours=random.randint(0, 2 * 365 * 24))
		availability.is_available(random.choice(names), f, f + timedelta(days=2))

	def one_search():
		f = start + timedelta(days=random.randint(0, 700))
		search.search(f, f + timedelta(days=3), rental_type=rental_type, limit=50)

	result = {
		"bookings": bookings,
		"units": units,
		"seed_seconds": seeded,
		"is_available_ms": _timed(one_check, samples),
		"search_ms": _timed(one_search, max(20, samples // 10)),
	}
	frappe.db.rollback()
	print(result)
	return result

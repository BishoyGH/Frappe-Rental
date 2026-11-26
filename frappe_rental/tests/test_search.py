import time

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime, random_string

from frappe_rental.api import availability as api
from frappe_rental.compat.erpnext import ensure_setup_complete
from frappe_rental.services import availability as av
from frappe_rental.services import search as svc
from frappe_rental.services.setup import create_defaults


def make(doctype, key, name, **kw):
	if not frappe.db.exists(doctype, name):
		frappe.get_doc({"doctype": doctype, key: name, **kw}).insert()
	return name


def item(rtype, card, **kw):
	return (
		frappe.get_doc(
			{
				"doctype": "Rental Item",
				"item_name": f"T15 {random_string(6)}",
				"rental_type": rtype,
				"rate_card": card,
				**kw,
			}
		)
		.insert()
		.name
	)


def unit(item_name, **kw):
	return (
		frappe.get_doc(
			{"doctype": "Rental Unit", "unit_name": f"T15 {random_string(6)}", "rental_item": item_name, **kw}
		)
		.insert()
		.name
	)


def hold(unit_name, start, end, qty=1, rtype="T15 Hourly"):
	source = f"T15-{random_string(8)}"
	av._insert(unit_name, *av.busy_window(start, end, rtype), qty, "Rental Booking", source, None)
	return source


class TestSearch(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		company = ensure_setup_complete()
		create_defaults()
		cur = frappe.db.get_value("Company", company, "default_currency")
		make(
			"Rental Rate Card",
			"card_name",
			"T15 Cheap",
			currency=cur,
			rates=[{"time_unit": "Hour", "rate": 10}],
		)
		make(
			"Rental Rate Card",
			"card_name",
			"T15 Dear",
			currency=cur,
			rates=[{"time_unit": "Hour", "rate": 30}],
		)
		make(
			"Rental Rate Card", "card_name", "T15 Days", currency=cur, rates=[{"time_unit": "Day", "rate": 5}]
		)
		for name, kw in (
			("T15 Hourly", {"buffer_after": 30}),
			("T15 Pool", {"identification_mode": "Pooled"}),
			("T15 Other", {}),
		):
			make("Rental Type", "type_name", name, mode="Resource", time_unit="Hour", **kw)
		cls.loc_a = make("Rental Location", "location_name", "T15 North", company=company)
		cls.loc_b = make("Rental Location", "location_name", "T15 South", company=company)

	def names(self, result):
		return [r["rental_unit"] for r in result]

	def test_free_units_ranked_by_price_then_location(self):
		cheap, dear = item("T15 Hourly", "T15 Cheap"), item("T15 Hourly", "T15 Dear")
		u_dear = unit(dear)
		u_cheap_b = unit(cheap, location=self.loc_b)
		u_cheap_a = unit(cheap, location=self.loc_a)
		busy = unit(cheap)
		hold(busy, "2026-06-01 10:00", "2026-06-01 12:00")
		result = svc.search("2026-06-01 10:00", "2026-06-01 12:00", rental_type="T15 Hourly")
		got = [n for n in self.names(result) if n in (u_dear, u_cheap_a, u_cheap_b, busy)]
		self.assertNotIn(busy, got)
		self.assertEqual(got[-1], u_dear)
		row = next(r for r in result if r["rental_unit"] == u_dear)
		self.assertEqual(row["price"], 60)
		ranked = svc.search("2026-06-01 10:00", "2026-06-01 12:00", rental_item=cheap, location=None)
		self.assertEqual(ranked[0]["price"], 20)
		# location filter keeps only that location
		north = svc.search("2026-06-01 10:00", "2026-06-01 12:00", rental_item=cheap, location=self.loc_a)
		self.assertEqual(self.names(north), [u_cheap_a])

	def test_buffers_and_adjacency(self):
		it = item("T15 Hourly", "T15 Cheap")
		u = unit(it)
		hold(u, "2026-06-02 10:00", "2026-06-02 12:00")  # busy until 12:30 with buffer
		self.assertNotIn(u, self.names(svc.search("2026-06-02 12:15", "2026-06-02 13:00", rental_item=it)))
		self.assertIn(u, self.names(svc.search("2026-06-02 12:30", "2026-06-02 13:00", rental_item=it)))
		self.assertIn(u, self.names(svc.search("2026-06-02 08:00", "2026-06-02 09:30", rental_item=it)))

	def test_mixed_types_and_pooled(self):
		pool_item = item("T15 Pool", "T15 Cheap")
		pool = unit(pool_item, identification_mode="Pooled", quantity_available=5)
		other = unit(item("T15 Other", "T15 Cheap"))
		hold(pool, "2026-06-03 10:00", "2026-06-03 12:00", qty=3, rtype="T15 Pool")
		result = svc.search("2026-06-03 11:00", "2026-06-03 13:00", qty=2)
		self.assertIn(pool, self.names(result))
		self.assertNotIn(other, self.names(result))  # qty 2 on an exclusive unit is not free
		row = next(r for r in result if r["rental_unit"] == pool)
		self.assertEqual(row["free_qty"], 2)
		self.assertNotIn(pool, self.names(svc.search("2026-06-03 11:00", "2026-06-03 13:00", qty=3)))

	def test_unavailable_status_and_blocks(self):
		it = item("T15 Other", "T15 Cheap")
		maint = unit(it, status="Maintenance")
		blocked = unit(it)
		frappe.get_doc(
			{
				"doctype": "Rental Block",
				"rental_unit": blocked,
				"from_datetime": "2026-06-04 00:00",
				"reason": "Maintenance",
			}
		).insert()
		names = self.names(svc.search("2026-07-01 10:00", "2026-07-01 11:00", rental_item=it))
		self.assertNotIn(maint, names)
		self.assertNotIn(blocked, names)  # open-ended block

	def test_no_price_ranked_last(self):
		days = item("T15 Hourly", "T15 Days")
		priced = item("T15 Hourly", "T15 Cheap")
		u_days, u_priced = unit(days), unit(priced)
		# a 2 hour booking against a Day-only card still prices (1 day); remove rates to force none
		frappe.db.delete("Rental Rate", {"parent": "T15 Days"})
		frappe.clear_document_cache("Rental Rate Card", "T15 Days")
		result = [
			r
			for r in svc.search("2026-06-05 10:00", "2026-06-05 12:00")
			if r["rental_unit"] in (u_days, u_priced)
		]
		self.assertEqual([r["rental_unit"] for r in result], [u_priced, u_days])
		self.assertIsNone(result[1]["price"])

	def test_calendar(self):
		it = item("T15 Other", "T15 Cheap")
		u1, u2 = unit(it), unit(it)
		hold(u1, "2026-08-10 00:00", "2026-08-12 00:00", rtype=None)
		hold(u2, "2026-08-10 09:00", "2026-08-10 17:00", rtype=None)
		cal = svc.calendar(2026, 8, rental_item=it)
		self.assertEqual(len(cal), 31)
		self.assertEqual(cal["2026-08-10"], {"free": 0, "partial": 1, "busy": 1, "total": 2})
		self.assertEqual(cal["2026-08-11"], {"free": 1, "partial": 0, "busy": 1, "total": 2})
		self.assertEqual(cal["2026-08-12"]["free"], 2)
		single = api.calendar("2026-08", rental_unit=u1)
		self.assertEqual(single["2026-08-11"]["busy"], 1)

	def test_api_validation_and_permissions(self):
		with self.assertRaises(frappe.ValidationError):
			api.search("2026-06-01 12:00", "2026-06-01 10:00")
		with self.assertRaises(frappe.ValidationError):
			api.search("2026-06-01 10:00", "2026-06-01 12:00", filters='{"name": "x"}')
		with self.assertRaises(frappe.ValidationError):
			api.calendar("2026-13")
		self.assertIsInstance(
			api.search("2026-06-01 10:00", "2026-06-01 12:00", filters='{"is_published": 0}'), list
		)
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				api.search("2026-06-01 10:00", "2026-06-01 12:00")
			with self.assertRaises(frappe.PermissionError):
				api.calendar("2026-08", rental_item="x")
		finally:
			frappe.set_user("Administrator")

	def test_performance_5000_units(self):
		it = item("T15 Other", "T15 Cheap")
		now = now_datetime()
		fields = [
			"name",
			"unit_name",
			"rental_item",
			"rental_type",
			"identification_mode",
			"status",
			"is_group",
			"lft",
			"rgt",
			"creation",
			"modified",
			"owner",
			"modified_by",
			"docstatus",
		]
		tag = random_string(4)
		rows = [
			(
				f"T15P-{tag}-{i:05d}",
				f"Perf {i}",
				it,
				"T15 Other",
				"None",
				"Available",
				0,
				0,
				0,
				now,
				now,
				"Administrator",
				"Administrator",
				0,
			)
			for i in range(5000)
		]
		frappe.db.bulk_insert("Rental Unit", fields, rows)
		for i in range(0, 5000, 3):  # a third of them busy
			hold(rows[i][0], "2026-09-01 10:00", "2026-09-01 12:00", rtype=None)
		svc.search("2026-09-01 10:00", "2026-09-01 11:00", rental_item=it)  # warm caches
		began = time.perf_counter()
		result = svc.search("2026-09-01 10:00", "2026-09-01 11:00", rental_item=it)
		elapsed = time.perf_counter() - began
		self.assertEqual(len(result), 5000 - len(range(0, 5000, 3)))
		self.assertLess(elapsed, 0.3, f"search took {elapsed:.3f}s")

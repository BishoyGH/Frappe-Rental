import threading
from datetime import datetime

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.compat.erpnext import ensure_setup_complete
from frappe_rental.services import availability as av


def fake_booking(unit, start, end, qty=1, rental_type="T13 Exclusive", item=None):
	return frappe._dict(
		name=f"T13-BK-{random_string(8)}",
		rental_type=rental_type,
		from_datetime=start,
		to_datetime=end,
		lines=[
			frappe._dict(
				idx=1,
				name=None,
				rental_item=item,
				rental_unit=unit,
				qty=qty,
				from_datetime=None,
				to_datetime=None,
			)
		],
	)


def make_type(name, **kw):
	if not frappe.db.exists("Rental Type", name):
		frappe.get_doc(
			{"doctype": "Rental Type", "type_name": name, "mode": "Resource", "time_unit": "Hour", **kw}
		).insert()
	return name


def make_unit(rtype, **kw):
	item = frappe.get_doc(
		{"doctype": "Rental Item", "item_name": f"T13 {random_string(5)}", "rental_type": rtype}
	).insert()
	unit = frappe.get_doc(
		{"doctype": "Rental Unit", "unit_name": f"T13 {random_string(5)}", "rental_item": item.name, **kw}
	).insert()
	return item.name, unit.name


class TestAvailability(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_setup_complete()
		make_type("T13 Exclusive")
		make_type("T13 Buffered", buffer_before=30, buffer_after=60)
		make_type("T13 Pooled", identification_mode="Pooled")

	def test_exclusive_overlap_and_adjacent(self):
		_, unit = make_unit("T13 Exclusive")
		av.reserve_booking(fake_booking(unit, "2026-03-02 10:00", "2026-03-02 12:00"))
		self.assertFalse(
			av.is_available(unit, "2026-03-02 11:00", "2026-03-02 13:00", rental_type="T13 Exclusive")
		)
		self.assertFalse(
			av.is_available(unit, "2026-03-02 09:00", "2026-03-02 14:00", rental_type="T13 Exclusive")
		)
		self.assertTrue(
			av.is_available(unit, "2026-03-02 12:00", "2026-03-02 13:00", rental_type="T13 Exclusive")
		)  # adjacent
		self.assertTrue(
			av.is_available(unit, "2026-03-02 08:00", "2026-03-02 10:00", rental_type="T13 Exclusive")
		)
		with self.assertRaises(av.UnavailableError):
			av.reserve_booking(fake_booking(unit, "2026-03-02 11:59", "2026-03-02 13:00"))

	def test_buffers(self):
		_, unit = make_unit("T13 Buffered")
		av.reserve_booking(
			fake_booking(unit, "2026-03-02 10:00", "2026-03-02 12:00", rental_type="T13 Buffered")
		)
		# 12:00 + 60 min after, next start 13:00 - 30 min before = 12:30 -> clash
		self.assertFalse(
			av.is_available(unit, "2026-03-02 13:00", "2026-03-02 14:00", rental_type="T13 Buffered")
		)
		self.assertTrue(
			av.is_available(unit, "2026-03-02 13:30", "2026-03-02 14:00", rental_type="T13 Buffered")
		)

	def test_pooled_peak_not_sum(self):
		_, unit = make_unit("T13 Pooled", quantity_available=10)
		av.reserve_booking(
			fake_booking(unit, "2026-03-02 08:00", "2026-03-02 10:00", qty=6, rental_type="T13 Pooled")
		)
		av.reserve_booking(
			fake_booking(unit, "2026-03-02 10:00", "2026-03-02 12:00", qty=6, rental_type="T13 Pooled")
		)
		# The two bookings never overlap each other, so 4 more fit across the whole morning.
		self.assertTrue(
			av.is_available(unit, "2026-03-02 08:00", "2026-03-02 12:00", qty=4, rental_type="T13 Pooled")
		)
		self.assertFalse(
			av.is_available(unit, "2026-03-02 09:00", "2026-03-02 11:00", qty=5, rental_type="T13 Pooled")
		)
		with self.assertRaises(av.UnavailableError):
			av.reserve_booking(
				fake_booking(unit, "2026-03-02 09:30", "2026-03-02 09:45", qty=5, rental_type="T13 Pooled")
			)

	def test_open_ended(self):
		_, unit = make_unit("T13 Exclusive")
		av.reserve_booking(fake_booking(unit, "2026-03-02 10:00", None))
		self.assertFalse(av.is_available(unit, "2030-01-01 00:00", "2030-01-02 00:00"))
		self.assertTrue(av.is_available(unit, "2026-03-01 00:00", "2026-03-02 10:00"))

	def test_block_and_status(self):
		_, unit = make_unit("T13 Pooled", quantity_available=5)
		block = frappe.get_doc(
			{
				"doctype": "Rental Block",
				"rental_unit": unit,
				"from_datetime": "2026-04-01 00:00",
				"to_datetime": "2026-04-02 00:00",
			}
		).insert()
		self.assertFalse(
			av.is_available(unit, "2026-04-01 12:00", "2026-04-01 13:00", rental_type="T13 Pooled")
		)
		block.delete()
		self.assertTrue(
			av.is_available(unit, "2026-04-01 12:00", "2026-04-01 13:00", rental_type="T13 Pooled")
		)
		frappe.db.set_value("Rental Unit", unit, "status", "Maintenance")
		self.assertFalse(
			av.is_available(unit, "2026-04-01 12:00", "2026-04-01 13:00", rental_type="T13 Pooled")
		)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Rental Block",
					"rental_unit": unit,
					"from_datetime": "2026-04-02",
					"to_datetime": "2026-04-01",
				}
			).insert()

	def test_reserve_is_idempotent_and_assigns_unit(self):
		item, unit = make_unit("T13 Exclusive")
		booking = fake_booking(None, "2026-05-01 10:00", "2026-05-01 11:00", item=item)
		av.reserve_booking(booking)
		self.assertEqual(booking.lines[0].rental_unit, unit)
		av.reserve_booking(booking)  # rerun replaces its own rows instead of clashing
		self.assertEqual(frappe.db.count(av.CACHE, {"source_name": booking.name}), 1)
		self.assertEqual(av.release("Rental Booking", booking.name), 1)
		self.assertEqual(av.free_units(item, "2026-05-01 10:00", "2026-05-01 11:00"), [unit])

	def test_dst_adjacent_in_utc(self):
		# Stored values are UTC: Berlin's 2026-03-29 02:00 jump does not create a gap or overlap.
		_, unit = make_unit("T13 Exclusive")
		av.reserve_booking(fake_booking(unit, "2026-03-28 23:00", "2026-03-29 01:00"))
		self.assertTrue(av.is_available(unit, "2026-03-29 01:00", "2026-03-29 03:00"))
		self.assertFalse(av.is_available(unit, "2026-03-29 00:59", "2026-03-29 03:00"))

	def test_peak_load_pure(self):
		t = lambda h: datetime(2026, 1, 1, h)  # noqa: E731
		rows = [
			{"busy_from": t(8), "busy_to": t(10), "qty": 3},
			{"busy_from": t(9), "busy_to": t(11), "qty": 2},
			{"busy_from": t(10), "busy_to": None, "qty": 4},
		]
		self.assertEqual(av.peak_load(rows, t(7), t(12)), 6)  # 10:00 to 11:00: 2 + 4
		self.assertEqual(av.peak_load(rows[:2], t(8), t(9)), 3)


class TestConcurrentBooking(FrappeTestCase):
	"""Parallel reservations on separate connections must never double-book."""

	def test_parallel_bookings_one_wins(self):
		ensure_setup_complete()
		make_type("T13 Exclusive")
		_, unit = make_unit("T13 Exclusive")
		frappe.db.commit()  # threads use their own connections and must see the fixtures
		site, sites_path = frappe.local.site, frappe.local.sites_path
		barrier = threading.Barrier(4)
		results = []

		def worker():
			frappe.init(site=site, sites_path=sites_path)
			frappe.connect()
			try:
				barrier.wait()
				av.reserve_booking(fake_booking(unit, "2026-06-01 10:00", "2026-06-01 12:00"))
				frappe.db.commit()
				results.append("ok")
			except av.UnavailableError:
				frappe.db.rollback()
				results.append("clash")
			except Exception as e:  # surface unexpected errors in the assertion message
				frappe.db.rollback()
				results.append(repr(e))
			finally:
				frappe.destroy()

		threads = [threading.Thread(target=worker) for _ in range(4)]
		try:
			for t in threads:
				t.start()
			for t in threads:
				t.join(60)
			self.assertEqual(sorted(results), ["clash", "clash", "clash", "ok"], results)
			self.assertEqual(frappe.db.count(av.CACHE, {"rental_unit": unit}), 1)
		finally:
			frappe.db.delete(av.CACHE, {"rental_unit": unit})
			frappe.db.commit()

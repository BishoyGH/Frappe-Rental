"""Housekeeping and turnaround (T51): task on return, unit status, overdue block, completion."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.services import availability, housekeeping
from frappe_rental.tests import test_erpnext_sync as t16

TYPE = "T51 Room"


class TestHousekeeping(FrappeTestCase):
	_tax_template = t16.TestErpnextSync.__dict__["_tax_template"]
	make_fixtures = t16.TestErpnextSync.__dict__["make_fixtures"]

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()
		if not frappe.db.exists("Rental Type", TYPE):
			frappe.get_doc(
				{
					"doctype": "Rental Type",
					"type_name": TYPE,
					"mode": "Resource",
					"time_unit": "Day",
					"requires_hold": 0,
					"identification_mode": "None",
					"buffer_after": 120,
					"housekeeping_task": 1,
				}
			).insert()

	def book(self, rtype=TYPE):
		item = frappe.get_doc(
			{
				"doctype": "Rental Item",
				"item_name": f"T51 {random_string(6)}",
				"rental_type": rtype,
				"rate_card": "T16 Card",
			}
		).insert()
		unit = frappe.get_doc(
			{"doctype": "Rental Unit", "unit_name": f"T51 {random_string(6)}", "rental_item": item.name}
		).insert()
		doc = frappe.get_doc(
			{
				"doctype": "Rental Booking",
				"customer": self.customer,
				"rental_type": rtype,
				"company": self.company,
				"from_datetime": "2026-07-01 10:00",
				"to_datetime": "2026-07-03 10:00",
				"lines": [{"rental_item": item.name, "rental_unit": unit.name, "qty": 1}],
			}
		).insert()
		doc.submit()
		return doc, unit.name

	def handover(self, booking, kind, when, unit, condition="Good"):
		doc = frappe.get_doc(
			{
				"doctype": "Rental Handover",
				"rental_booking": booking.name,
				"handover_type": kind,
				"posted_on": when,
				"lines": [{"rental_unit": unit, "condition": condition}],
				"checklist": [{"check": "Clean", "done": 1}],
				"signed_by": "Customer",
			}
		)
		doc.insert()
		doc.submit()
		return doc

	def tasks(self, unit):
		return frappe.get_all(
			housekeeping.DOCTYPE,
			filters={"rental_unit": unit},
			fields=["name", "status", "due_by", "rental_block"],
		)

	def test_return_creates_task_and_turnaround(self):
		booking, unit = self.book()
		self.handover(booking, "Check-out", "2026-07-01 10:00", unit)
		back = self.handover(booking, "Return", "2026-07-03 10:00", unit)
		tasks = self.tasks(unit)
		self.assertEqual(len(tasks), 1)
		self.assertEqual(str(tasks[0].due_by), "2026-07-03 12:00:00")
		self.assertEqual(frappe.db.get_value("Rental Unit", unit, "status"), "Turnaround")
		self.assertEqual(housekeeping.on_return(back, booking), [tasks[0].name])  # idempotent

		housekeeping.complete(tasks[0].name, "Done")
		self.assertEqual(frappe.db.get_value("Rental Unit", unit, "status"), "Available")
		housekeeping.complete(tasks[0].name)  # no-op

	def test_overdue_task_blocks_until_done(self):
		booking, unit = self.book()
		self.handover(booking, "Check-out", "2026-07-01 10:00", unit)
		self.handover(booking, "Return", "2026-07-03 10:00", unit)
		self.assertTrue(availability.is_available(unit, "2026-07-03 13:00", "2026-07-04 10:00"))
		self.assertEqual(housekeeping.check_overdue("2026-07-03 11:00"), 0)
		self.assertEqual(housekeeping.check_overdue("2026-07-03 13:00"), 1)
		self.assertEqual(housekeeping.check_overdue("2026-07-03 14:00"), 0)  # once
		self.assertFalse(availability.is_available(unit, "2026-07-03 13:00", "2026-07-04 10:00"))
		self.assertFalse(availability.is_available(unit, "2027-01-01 10:00", "2027-01-02 10:00"))

		task = self.tasks(unit)[0]
		frappe.db.set_value(housekeeping.DOCTYPE, task.name, "completed_on", "2026-07-03 15:00")
		housekeeping.complete(task.name)
		self.assertEqual(
			str(frappe.db.get_value("Rental Block", task.rental_block, "to_datetime")), "2026-07-03 15:00:00"
		)
		self.assertTrue(availability.is_available(unit, "2026-07-03 16:00", "2026-07-04 10:00"))

	def test_damaged_return_and_disabled_types_get_no_task(self):
		booking, unit = self.book()
		self.handover(booking, "Check-out", "2026-07-01 10:00", unit)
		self.handover(booking, "Return", "2026-07-03 10:00", unit, condition="Damaged")
		self.assertEqual(self.tasks(unit), [])
		self.assertEqual(frappe.db.get_value("Rental Unit", unit, "status"), "Maintenance")

		other, other_unit = self.book("T16 Device")
		self.handover(other, "Check-out", "2026-07-01 10:00", other_unit)
		self.handover(other, "Return", "2026-07-03 10:00", other_unit)
		self.assertEqual(self.tasks(other_unit), [])

	def test_cancel_return_removes_open_task(self):
		booking, unit = self.book()
		self.handover(booking, "Check-out", "2026-07-01 10:00", unit)
		back = self.handover(booking, "Return", "2026-07-03 10:00", unit)
		back.cancel()
		self.assertEqual(self.tasks(unit), [])

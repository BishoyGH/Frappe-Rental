"""Metered usage (T49): readings at handover and by API, allowance, overage billed once."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, random_string

from frappe_rental.services import metering
from frappe_rental.tests import test_erpnext_sync as t16
from frappe_rental.tests.test_contracts import make_contract

TYPE = "T49 Car"


class TestMetering(FrappeTestCase):
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
					"meter_unit": "Km",
					"included_allowance": 100,
					"overage_rate": 2,
				}
			).insert()

	def book(self, **kw):
		item = frappe.get_doc(
			{
				"doctype": "Rental Item",
				"item_name": f"T49 {random_string(6)}",
				"rental_type": TYPE,
				"rate_card": "T16 Card",
			}
		).insert()
		unit = frappe.get_doc(
			{"doctype": "Rental Unit", "unit_name": f"T49 {random_string(6)}", "rental_item": item.name}
		).insert()
		doc = frappe.get_doc(
			{
				"doctype": "Rental Booking",
				"customer": self.customer,
				"rental_type": TYPE,
				"company": self.company,
				"from_datetime": "2026-07-01 10:00",
				"to_datetime": "2026-07-03 10:00",
				"lines": [{"rental_item": item.name, "rental_unit": unit.name, "qty": 1}],
				**kw,
			}
		).insert()
		doc.submit()
		return doc, unit.name

	def handover(self, booking, kind, when, unit, km):
		doc = frappe.get_doc(
			{
				"doctype": "Rental Handover",
				"rental_booking": booking.name,
				"handover_type": kind,
				"posted_on": when,
				"lines": [{"rental_unit": unit, "condition": "Good", "meter_reading": km}],
				"checklist": [{"check": "Clean", "done": 1}],
				"signed_by": "Customer",
			}
		)
		doc.insert()
		doc.submit()
		return doc

	def overage(self, booking):
		return frappe.get_all(
			"Rental Billable Event",
			filters={"rental_booking": booking, "event_type": "Overage"},
			fields=["name", "amount", "status"],
		)

	def test_overage_from_handover_readings(self):
		booking, unit = self.book()
		self.handover(booking, "Check-out", "2026-07-01 10:00", unit, 1000)
		metering.record(booking.name, unit, 1080, "API", "2026-07-02 10:00")
		s = metering.summary(booking.name)
		self.assertEqual((s["total"], s["overage"], s["amount"]), (80, 0, 0))
		back = self.handover(booking, "Return", "2026-07-03 10:00", unit, 1150)
		s = metering.summary(booking.name)
		self.assertEqual((s["total"], s["overage"], s["amount"], s["meter_unit"]), (150, 50, 100, "Km"))
		events = self.overage(booking.name)
		self.assertEqual([flt(e.amount) for e in events], [100])
		metering.settle(booking.name)
		self.assertEqual(len(self.overage(booking.name)), 1)  # once

		back.cancel()
		self.assertEqual(self.overage(booking.name), [])
		self.assertEqual(metering.usage(booking.name)["total"], 80)

	def test_readings_cannot_go_back_or_be_off_booking(self):
		booking, unit = self.book()
		metering.record(booking.name, unit, 500, "API", "2026-07-01 11:00")
		with self.assertRaises(frappe.ValidationError):
			metering.record(booking.name, unit, 400, "API", "2026-07-01 12:00")
		other, other_unit = self.book()
		with self.assertRaises(frappe.ValidationError):
			metering.record(booking.name, other_unit, 600, "API", "2026-07-01 12:00")

	def test_within_allowance_bills_nothing(self):
		booking, unit = self.book()
		self.handover(booking, "Check-out", "2026-07-01 10:00", unit, 10)
		self.handover(booking, "Return", "2026-07-03 10:00", unit, 90)
		self.assertEqual(self.overage(booking.name), [])

	def test_contract_terms_override_type(self):
		from frappe_rental.services import contracts

		contract = make_contract(
			customer=self.customer, included_allowance=10, allowance_unit="Km", overage_rate=5
		)
		contracts.send_for_signature(contract)
		contracts.activate(contract, "Jane")
		booking, unit = self.book(rental_contract=contract.name)
		metering.record(booking.name, unit, 0, "API", "2026-07-01 11:00")
		metering.record(booking.name, unit, 30, "API", "2026-07-02 11:00")
		s = metering.summary(booking.name)
		self.assertEqual((s["allowance"], s["rate"], s["amount"]), (10, 5, 100))

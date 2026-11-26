"""Call-off bookings (T43): bookings against allocations, allowance and overage, inherited rates."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from frappe_rental.services import calloff
from frappe_rental.tests import test_allocations as t42
from frappe_rental.tests import test_erpnext_sync as t16


class TestCalloff(FrappeTestCase):
	_tax_template = t16.TestErpnextSync.__dict__["_tax_template"]
	make_fixtures = t16.TestErpnextSync.__dict__["make_fixtures"]
	unit = t42.TestAllocations.unit

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()

	def active(self, rows, **kw):
		from frappe_rental.services import contracts
		from frappe_rental.tests.test_contracts import make_contract

		doc = make_contract(allocations=rows, **kw)
		frappe.db.set_value("Rental Contract", doc.name, "customer", self.customer)
		doc.reload()
		contracts.send_for_signature(doc)
		contracts.activate(doc, "Jane")
		doc.reload()
		return doc

	def booking(
		self, contract, row, unit=None, item=None, start="2026-03-01 10:00", end="2026-03-03 10:00", qty=1
	):
		item = item or frappe.db.get_value("Rental Unit", unit, "rental_item")
		return frappe.get_doc(
			{
				"doctype": "Rental Booking",
				"customer": self.customer,
				"rental_type": frappe.db.get_value("Rental Item", item, "rental_type"),
				"company": self.company,
				"from_datetime": start,
				"to_datetime": end,
				"rental_contract": contract.name,
				"contract_allocation": row,
				"lines": [{"rental_item": item, "rental_unit": unit, "qty": qty}],
			}
		).insert()

	def test_specific_unit_calloff_uses_own_allocation(self):
		unit = self.unit()
		doc = self.active([{"allocation_type": "Specific unit", "rental_unit": unit, "rate_override": 40}])
		b = self.booking(doc, doc.allocations[0].name, unit=unit)
		b.submit()
		self.assertEqual(b.status, "Confirmed")
		self.assertEqual(flt(b.lines[0].rate), 40)
		self.assertEqual(flt(b.lines[0].amount), 80)  # 2 days at the contract rate

	def test_outside_period_and_wrong_unit_rejected(self):
		unit, other = self.unit(), self.unit()
		doc = self.active(
			[{"allocation_type": "Specific unit", "rental_unit": unit, "to_date": "2026-03-31"}]
		)
		with self.assertRaises(frappe.ValidationError):
			self.booking(
				doc, doc.allocations[0].name, unit=unit, start="2026-04-02 10:00", end="2026-04-03 10:00"
			)
		with self.assertRaises(frappe.ValidationError):
			self.booking(doc, doc.allocations[0].name, unit=other)

	def test_category_caps_concurrent_units(self):
		a, b = self.unit(), self.unit()
		item_a = frappe.db.get_value("Rental Unit", a, "rental_item")
		frappe.db.set_value("Rental Unit", b, "rental_item", item_a)
		doc = self.active([{"allocation_type": "Category", "rental_item": item_a, "qty": 1}])
		self.booking(doc, doc.allocations[0].name, unit=a).submit()
		with self.assertRaises(frappe.ValidationError):
			self.booking(doc, doc.allocations[0].name, unit=b).submit()
		self.booking(
			doc, doc.allocations[0].name, unit=b, start="2026-05-01 10:00", end="2026-05-02 10:00"
		).submit()

	def test_allowance_and_overage(self):
		unit = self.unit()
		doc = self.active(
			[{"allocation_type": "Provider time", "rental_unit": None, "capacity": 60, "exclusive": 0}],
			overage_rate=5,
		)
		row = doc.allocations[0].name
		first = self.booking(doc, row, unit=unit)  # 48 h
		first.submit()
		self.assertEqual(calloff.remaining(doc.name, row), 12)
		self.assertFalse(frappe.db.exists("Rental Billable Event", {"source_name": first.name}))
		second = self.booking(
			doc, row, unit=unit, start="2026-04-01 10:00", end="2026-04-02 10:00"
		)  # 24 h, 12 over
		second.submit()
		event = frappe.get_all(
			"Rental Billable Event", filters={"source_name": second.name}, fields=["amount", "status"]
		)
		self.assertEqual([(flt(e.amount), e.status) for e in event], [(60.0, "Pending")])
		second.reload()
		second.cancel()
		self.assertEqual(calloff.remaining(doc.name, row), 12)
		self.assertEqual(
			frappe.db.get_value("Rental Billable Event", {"source_name": second.name}, "status"), "Cancelled"
		)

	def test_inactive_contract_rejected(self):
		unit = self.unit()
		doc = self.active([{"allocation_type": "Specific unit", "rental_unit": unit}])
		from frappe_rental.services import contracts

		contracts.terminate(doc, "done")
		with self.assertRaises(frappe.ValidationError):
			self.booking(doc, doc.allocations[0].name, unit=unit)

"""Contract allocations (T42): exclusive rows block availability; guards; release and swap."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.services import allocations, availability, contracts
from frappe_rental.tests import test_erpnext_sync as t16
from frappe_rental.tests.test_contracts import make_contract


class TestAllocations(FrappeTestCase):
	_tax_template = t16.TestErpnextSync.__dict__["_tax_template"]
	make_fixtures = t16.TestErpnextSync.__dict__["make_fixtures"]

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()

	def unit(self, rtype="T16 Device", **kw):
		item = frappe.get_doc(
			{
				"doctype": "Rental Item",
				"item_name": f"T42 {random_string(6)}",
				"rental_type": rtype,
				"rate_card": "T16 Card",
			}
		).insert()
		return (
			frappe.get_doc(
				{
					"doctype": "Rental Unit",
					"unit_name": f"T42 {random_string(6)}",
					"rental_item": item.name,
					**kw,
				}
			)
			.insert()
			.name
		)

	def active(self, rows):
		doc = make_contract(allocations=rows)
		contracts.send_for_signature(doc)
		contracts.activate(doc, "Jane")
		doc.reload()
		return doc

	def booking(self, unit, start="2026-03-01 10:00", end="2026-03-03 10:00"):
		return frappe.get_doc(
			{
				"doctype": "Rental Booking",
				"customer": self.customer,
				"rental_type": "T16 Device",
				"company": self.company,
				"from_datetime": start,
				"to_datetime": end,
				"lines": [
					{
						"rental_item": frappe.db.get_value("Rental Unit", unit, "rental_item"),
						"rental_unit": unit,
						"qty": 1,
					}
				],
			}
		).insert()

	def test_exclusive_allocation_blocks_calendar(self):
		unit = self.unit()
		doc = self.active([{"allocation_type": "Specific unit", "rental_unit": unit}])
		self.assertEqual(doc.allocations[0].status, "Active")
		self.assertFalse(availability.is_available(unit, "2026-03-01 10:00", "2026-03-03 10:00"))
		self.assertTrue(availability.is_available(unit, "2027-03-01 10:00", "2027-03-03 10:00"))
		with self.assertRaises(frappe.ValidationError):
			self.booking(unit).submit()

	def test_over_allocation_guard(self):
		unit = self.unit()
		self.active([{"allocation_type": "Specific unit", "rental_unit": unit}])
		with self.assertRaises(availability.UnavailableError):
			self.active(
				[
					{
						"allocation_type": "Specific unit",
						"rental_unit": unit,
						"from_date": "2026-06-01",
						"to_date": "2026-06-30",
					}
				]
			)

	def test_entitlements_do_not_block(self):
		unit = self.unit()
		item = frappe.db.get_value("Rental Unit", unit, "rental_item")
		self.active([{"allocation_type": "Category", "rental_item": item, "qty": 2}])
		self.assertTrue(availability.is_available(unit, "2026-03-01 10:00", "2026-03-03 10:00"))

	def test_pooled_quantity_limited_to_stock(self):
		pool = self.unit("T16 Pool", quantity_available=3)
		self.active([{"allocation_type": "Quantity", "rental_unit": pool, "qty": 2}])
		with self.assertRaises(availability.UnavailableError):
			self.active([{"allocation_type": "Quantity", "rental_unit": pool, "qty": 2}])

	def test_swap_end_to_end(self):
		old, new = self.unit(), self.unit()
		doc = self.active([{"allocation_type": "Specific unit", "rental_unit": old}])
		row = allocations.swap(doc, doc.allocations[0].name, new, "2026-07-01", "Broken screen")
		doc.reload()
		first, second = doc.allocations
		self.assertEqual((first.status, str(first.to_date)), ("Swapped", "2026-06-30"))
		self.assertEqual((second.name, second.rental_unit, second.swapped_from), (row, new, first.name))
		self.assertFalse(availability.is_available(old, "2026-03-01 10:00", "2026-03-02 10:00"))
		self.assertTrue(availability.is_available(old, "2026-08-01 10:00", "2026-08-02 10:00"))
		self.assertTrue(availability.is_available(new, "2026-03-01 10:00", "2026-03-02 10:00"))
		self.assertFalse(availability.is_available(new, "2026-08-01 10:00", "2026-08-02 10:00"))

	def test_release_and_terminate_free_units(self):
		a, b = self.unit(), self.unit()
		doc = self.active(
			[
				{"allocation_type": "Specific unit", "rental_unit": a},
				{"allocation_type": "Specific unit", "rental_unit": b},
			]
		)
		allocations.release(doc, doc.allocations[0].name, "2026-05-01")
		self.assertTrue(availability.is_available(a, "2026-06-01 10:00", "2026-06-02 10:00"))
		contracts.terminate(doc, "Ended early")
		self.assertTrue(availability.is_available(b, "2026-06-01 10:00", "2026-06-02 10:00"))

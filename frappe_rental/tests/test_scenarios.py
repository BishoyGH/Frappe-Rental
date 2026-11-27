"""Phase 1 acceptance (T21): book and invoice end to end with the Device and Apartment presets."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from frappe_rental.services import demo, erpnext_sync, lifecycle


class TestPhase1Scenarios(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.data = demo.make_demo()

	def test_demo_is_idempotent(self):
		before = frappe.db.count("Rental Unit")
		again = demo.make_demo()
		self.assertEqual(again["items"], self.data["items"])
		self.assertEqual(frappe.db.count("Rental Unit"), before)

	def test_device_rental_three_days(self):
		customer = self.data["customers"][0]
		name = demo.book(
			customer, "Device", self.data["items"]["Device"], "2027-09-01 10:00", "2027-09-04 10:00"
		)
		doc = frappe.get_doc("Rental Booking", name)
		self.assertEqual(doc.status, "Confirmed")
		self.assertEqual(flt(doc.net_total), 3 * 630)
		so = frappe.get_doc("Sales Order", doc.sales_order)
		self.assertEqual(so.docstatus, 1)
		self.assertEqual(flt(so.grand_total), flt(doc.grand_total))
		invoice = frappe.get_doc("Sales Invoice", erpnext_sync.make_sales_invoice(doc, submit=True))
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual(flt(invoice.grand_total), flt(doc.grand_total))
		self.assertEqual(invoice.customer, customer)
		# Running it again returns the same invoice
		self.assertEqual(erpnext_sync.make_sales_invoice(doc, submit=True), invoice.name)

	def test_apartment_month_needs_signed_contract(self):
		customer = self.data["customers"][1]
		item = self.data["items"]["Apartment"]
		with self.assertRaises(frappe.ValidationError):
			demo.book(customer, "Apartment", item, "2027-10-01 14:00", "2027-11-01 14:00")
		contract = demo.signed_contract(customer, "2027-10-01")
		name = demo.book(
			customer, "Apartment", item, "2027-10-01 14:00", "2027-11-01 14:00", contract=contract
		)
		doc = frappe.get_doc("Rental Booking", name)
		self.assertEqual(doc.status, "Confirmed")
		self.assertEqual(flt(doc.net_total), 16000)
		invoice = erpnext_sync.make_sales_invoice(doc, submit=True)
		self.assertEqual(
			flt(frappe.db.get_value("Sales Invoice", invoice, "grand_total")), flt(doc.grand_total)
		)
		# Cancel: the unpaid invoice and the order are cancelled, the unit is free again
		lifecycle.cancel(doc)
		self.assertEqual(frappe.db.get_value("Sales Invoice", invoice, "docstatus"), 2)
		self.assertFalse(frappe.db.exists("Rental Availability Cache", {"source_name": name}))

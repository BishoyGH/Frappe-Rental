"""Consolidated invoices (T50): one invoice per customer per run, per-line references, totals."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from frappe_rental.services import invoicing
from frappe_rental.tests import test_erpnext_sync as t16
from frappe_rental.tests import test_invoicing as t23
from frappe_rental.tests.utils import make_customer

T23 = t23.TestInvoicing.__dict__


class TestConsolidated(FrappeTestCase):
	_tax_template = t16.TestErpnextSync.__dict__["_tax_template"]
	make_fixtures = t16.TestErpnextSync.__dict__["make_fixtures"]
	monthly_booking = T23["monthly_booking"]

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()

	def setUp(self):
		self.customer = make_customer()
		frappe.db.set_value("Customer", self.customer, "rental_consolidate_invoices", 1)

	def test_one_invoice_with_per_line_references(self):
		a = self.monthly_booking(taxes=True)
		b = self.monthly_booking(taxes=True)
		invoicing.run_due_invoices("2026-01-15")
		a.reload()
		b.reload()
		si_name = a.billing_schedule[0].sales_invoice
		self.assertTrue(si_name)
		self.assertEqual(b.billing_schedule[0].sales_invoice, si_name)
		si = frappe.get_doc("Sales Invoice", si_name)
		self.assertFalse(si.rental_booking)
		self.assertEqual({i.rental_booking for i in si.items}, {a.name, b.name})
		self.assertEqual(
			{i.rental_billing_row for i in si.items}, {a.billing_schedule[0].name, b.billing_schedule[0].name}
		)
		expected = flt(a.billing_schedule[0].amount) + flt(b.billing_schedule[0].amount)
		self.assertEqual(flt(si.net_total, 2), flt(expected, 2))
		self.assertTrue(si.taxes)
		self.assertEqual(flt(si.grand_total, 2), flt(expected * 1.1, 2))

		invoicing.run_due_invoices("2026-01-15")  # rerun bills nothing more
		count = frappe.db.count("Sales Invoice", {"customer": self.customer, "docstatus": 1})
		self.assertEqual(count, 1)

		invoicing.run_due_invoices("2026-12-31")
		total = sum(
			flt(v)
			for v in frappe.get_all(
				"Sales Invoice", filters={"customer": self.customer, "docstatus": 1}, pluck="net_total"
			)
		)
		self.assertEqual(flt(total, 2), flt(flt(a.net_total) + flt(b.net_total), 2))
		self.assertEqual(frappe.db.count("Sales Invoice", {"customer": self.customer, "docstatus": 1}), 3)

	def test_pending_events_join_with_reference(self):
		from frappe_rental.services import billable_events

		a = self.monthly_booking()
		b = self.monthly_booking()
		billable_events.add(a.name, "Delivery", 40, "Delivery", event_date="2026-01-01")
		invoicing.run_due_invoices("2026-01-15")
		a.reload()
		si = frappe.get_doc("Sales Invoice", a.billing_schedule[0].sales_invoice)
		delivery = [i for i in si.items if i.item_code == "Rental Delivery"]
		self.assertEqual([(i.rental_booking, flt(i.rate)) for i in delivery], [(a.name, 40)])
		b.reload()
		self.assertEqual(b.billing_schedule[0].sales_invoice, si.name)

	def test_other_customers_keep_one_invoice_per_booking(self):
		frappe.db.set_value("Customer", self.customer, "rental_consolidate_invoices", 0)
		a = self.monthly_booking()
		b = self.monthly_booking()
		invoicing.run_due_invoices("2026-01-15")
		a.reload()
		b.reload()
		self.assertNotEqual(a.billing_schedule[0].sales_invoice, b.billing_schedule[0].sales_invoice)
		self.assertEqual(
			frappe.db.get_value("Sales Invoice", a.billing_schedule[0].sales_invoice, "rental_booking"),
			a.name,
		)

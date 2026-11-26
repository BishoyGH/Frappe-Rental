"""Billable events (T24): queued charges are invoiced once, on the right income account."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from frappe_rental.services import billable_events, invoicing
from frappe_rental.tests import test_erpnext_sync as t16
from frappe_rental.tests import test_invoicing as t23


class TestBillableEvents(FrappeTestCase):
	_tax_template = t16.TestErpnextSync.__dict__["_tax_template"]
	make_fixtures = t16.TestErpnextSync.__dict__["make_fixtures"]
	booking = t16.TestErpnextSync.booking
	monthly_booking = t23.TestInvoicing.monthly_booking

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()
		settings = frappe.get_single("Rental Settings")
		cls.late_account = settings.late_fee_income_account
		cls.damage_account = settings.damage_recovery_account

	def items_for(self, si, rate):
		return [i for i in frappe.get_doc("Sales Invoice", si).items if flt(i.rate) == rate]

	def test_event_joins_next_period_invoice(self):
		doc = self.monthly_booking()
		ev = billable_events.add(doc.name, "Late fee", 40, event_date="2026-01-20")
		invoicing.run_due_invoices("2026-01-10")
		self.assertEqual(frappe.db.get_value("Rental Billable Event", ev, "status"), "Pending")
		invoicing.run_due_invoices("2026-02-02")
		row = frappe.get_doc("Rental Billable Event", ev)
		self.assertEqual(row.status, "Invoiced")
		doc.reload()
		self.assertEqual(row.sales_invoice, doc.billing_schedule[1].sales_invoice)
		item = self.items_for(row.sales_invoice, 40)[0]
		if self.late_account and frappe.db.get_value("Account", self.late_account, "company") == self.company:
			self.assertEqual(item.income_account, self.late_account)

	def test_event_billed_once_on_rerun(self):
		doc = self.monthly_booking()
		billable_events.add(doc.name, "Delivery", 15, event_date="2026-01-01")
		invoicing.run_due_invoices("2026-01-02")
		invoicing.run_due_invoices("2026-01-02")
		billed = frappe.get_all(
			"Sales Invoice Item",
			filters={
				"rate": 15,
				"parent": ["in", frappe.get_all("Sales Invoice", {"rental_booking": doc.name}, pluck="name")],
			},
		)
		self.assertEqual(len(billed), 1)

	def test_leftover_events_get_own_invoice(self):
		doc = self.booking(taxes=False)  # one-off: the whole-booking row leaves no planned row
		invoicing.run_due_invoices("2027-01-01")
		ev = billable_events.add(doc.name, "Damage", 70, event_date="2026-06-01")
		si = invoicing.invoice_events(doc, "2027-01-01")  # raises, unlike the job, so failures show
		row = frappe.get_doc("Rental Billable Event", ev)
		self.assertEqual(row.status, "Invoiced")
		self.assertEqual(row.sales_invoice, si)
		self.assertNotEqual(row.sales_invoice, doc.sales_invoice)
		item = self.items_for(row.sales_invoice, 70)[0]
		if (
			self.damage_account
			and frappe.db.get_value("Account", self.damage_account, "company") == self.company
		):
			self.assertEqual(item.income_account, self.damage_account)
		self.assertIsNone(invoicing.invoice_events(doc, "2027-01-01"))

	def test_add_is_idempotent_per_source(self):
		doc = self.booking(taxes=False)
		a = billable_events.add(doc.name, "Late fee", 10, source=doc)
		b = billable_events.add(doc.name, "Late fee", 10, source=doc)
		self.assertEqual(a, b)

	def test_amount_must_be_positive(self):
		doc = self.booking(taxes=False)
		with self.assertRaises(frappe.ValidationError):
			billable_events.add(doc.name, "Other", 0)

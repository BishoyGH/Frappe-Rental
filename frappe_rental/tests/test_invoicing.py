"""Scheduled invoicing job (T23): reruns never double-bill; extension, shortening, early return."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, random_string

from frappe_rental.services import invoicing
from frappe_rental.tests import test_erpnext_sync as t16

MONTHLY = {"frequency": "Monthly", "alignment": "Calendar period start", "timing": "In advance"}


def flt2(v):
	return flt(v, 2)


class TestInvoicing(FrappeTestCase):
	"""Reuses the T16 fixtures (company, card at 100/day, cleaning charge, tax template), not its tests."""

	_tax_template = t16.TestErpnextSync.__dict__["_tax_template"]
	make_fixtures = t16.TestErpnextSync.__dict__["make_fixtures"]
	booking = t16.TestErpnextSync.booking

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()

	def monthly_booking(self, start="2026-01-01 00:00", end="2026-04-01 00:00", taxes=False):
		item = frappe.get_doc(
			{
				"doctype": "Rental Item",
				"item_name": f"T23 {random_string(6)}",
				"rental_type": "T16 Device",
				"rate_card": "T16 Card",
			}
		).insert()
		unit = frappe.get_doc(
			{"doctype": "Rental Unit", "unit_name": f"T23 {random_string(6)}", "rental_item": item.name}
		).insert()
		doc = frappe.get_doc(
			{
				"doctype": "Rental Booking",
				"customer": self.customer,
				"rental_type": "T16 Device",
				"company": self.company,
				"from_datetime": start,
				"to_datetime": end,
				"taxes_and_charges": self.tax if taxes else None,
				"lines": [{"rental_item": item.name, "rental_unit": unit.name, "qty": 1}],
				"billing_plan": [MONTHLY],
			}
		).insert()
		doc.submit()
		doc.reload()
		return doc

	def invoices(self, doc, is_return=0):
		return frappe.get_all(
			"Sales Invoice",
			filters={"rental_booking": doc.name, "docstatus": 1, "is_return": is_return},
			pluck="name",
		)

	def test_schedule_built_and_sums_to_net(self):
		doc = self.monthly_booking()
		self.assertEqual(len(doc.billing_schedule), 3)
		self.assertEqual(flt2(sum(r.amount for r in doc.billing_schedule)), flt2(doc.net_total))

	def test_job_bills_due_rows_once(self):
		doc = self.monthly_booking(taxes=True)
		made = invoicing.run_due_invoices("2026-02-15")
		self.assertEqual(len(self.invoices(doc)), 2)
		self.assertTrue(set(self.invoices(doc)) <= set(made))
		invoicing.run_due_invoices("2026-02-15")  # rerun
		self.assertEqual(len(self.invoices(doc)), 2)
		doc.reload()
		self.assertEqual([r.status for r in doc.billing_schedule], ["Invoiced", "Invoiced", "Planned"])
		si = frappe.get_doc("Sales Invoice", doc.billing_schedule[0].sales_invoice)
		self.assertEqual(flt2(si.net_total), flt2(doc.billing_schedule[0].amount))
		self.assertEqual(si.rental_billing_row, doc.billing_schedule[0].name)
		# invoice_row on an already billed row returns the same invoice
		self.assertEqual(invoicing.invoice_row(doc.billing_schedule[0].name), si.name)

	def test_all_rows_total_equals_booking(self):
		doc = self.monthly_booking()
		invoicing.run_due_invoices("2026-12-31")
		total = sum(flt(frappe.db.get_value("Sales Invoice", n, "net_total")) for n in self.invoices(doc))
		self.assertEqual(flt2(total), flt2(doc.net_total))

	def test_extension_adds_rows(self):
		doc = self.monthly_booking()
		invoicing.run_due_invoices("2026-01-10")
		doc.reload()
		invoicing.reschedule(doc, to_datetime="2026-05-01 00:00", net_total=flt(doc.net_total) + 3000)
		doc.reload()
		self.assertEqual(len(doc.billing_schedule), 4)
		self.assertEqual(doc.billing_schedule[0].status, "Invoiced")
		self.assertEqual(flt2(sum(r.amount for r in doc.billing_schedule)), flt2(doc.net_total))

	def test_shortening_rebuilds_planned_rows(self):
		doc = self.monthly_booking()
		invoicing.run_due_invoices("2026-01-10")
		doc.reload()
		first = flt(doc.billing_schedule[0].amount)
		invoicing.reschedule(doc, to_datetime="2026-02-15 00:00", net_total=first + 1400)
		doc.reload()
		self.assertEqual(len(doc.billing_schedule), 2)
		self.assertEqual(flt2(doc.billing_schedule[1].amount), 1400)

	def test_early_return_credits_overbilling(self):
		doc = self.monthly_booking()
		invoicing.run_due_invoices("2026-03-05")  # all three months billed
		doc.reload()
		billed = sum(flt(r.amount) for r in doc.billing_schedule)
		invoicing.reschedule(doc, to_datetime="2026-02-01 00:00", net_total=billed - 500)
		doc.reload()
		credit = [r for r in doc.billing_schedule if flt(r.amount) < 0]
		self.assertEqual(len(credit), 1)
		self.assertEqual(credit[0].status, "Credited")
		note = frappe.get_doc("Sales Invoice", credit[0].sales_invoice)
		self.assertEqual(note.is_return, 1)
		self.assertEqual(flt2(note.net_total), -500)

	def test_one_off_row_uses_sales_order_invoice(self):
		doc = self.booking(taxes=False)
		self.assertEqual(len(doc.billing_schedule), 1)
		invoicing.run_due_invoices("2027-01-01")
		doc.reload()
		self.assertEqual(doc.billing_schedule[0].status, "Invoiced")
		self.assertEqual(doc.billing_schedule[0].sales_invoice, doc.sales_invoice)
		self.assertEqual(len(self.invoices(doc)), 1)

	def test_draft_setting(self):
		frappe.db.set_single_value("Rental Settings", "submit_scheduled_invoices", 0)
		try:
			doc = self.monthly_booking()
			invoicing.run_due_invoices("2026-01-02")
		finally:
			frappe.db.set_single_value("Rental Settings", "submit_scheduled_invoices", 1)
		doc.reload()
		si = doc.billing_schedule[0].sales_invoice
		self.assertEqual(frappe.db.get_value("Sales Invoice", si, "docstatus"), 0)

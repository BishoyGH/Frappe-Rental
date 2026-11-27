"""Renewal and termination (T44): scheduled job with frozen dates, indexation, fees, closure."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from frappe_rental.services import availability, contracts, invoicing, renewal
from frappe_rental.tests import test_allocations as t42
from frappe_rental.tests import test_erpnext_sync as t16
from frappe_rental.tests.test_contracts import make_contract


class TestRenewal(FrappeTestCase):
	_tax_template = t16.TestErpnextSync.__dict__["_tax_template"]
	make_fixtures = t16.TestErpnextSync.__dict__["make_fixtures"]
	unit = t42.TestAllocations.unit

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()

	def active(self, **kw):
		doc = make_contract(**kw)
		contracts.send_for_signature(doc)
		contracts.activate(doc, "Jane")
		doc.reload()
		return doc

	def test_notice_then_end_without_renewal(self):
		unit = self.unit()
		doc = self.active(
			notice_period_days=30, allocations=[{"allocation_type": "Specific unit", "rental_unit": unit}]
		)
		renewal.run("2026-11-15")
		self.assertEqual(frappe.db.get_value("Rental Contract", doc.name, "status"), "Active")
		out = renewal.run("2026-12-01")
		self.assertIn(doc.name, out["notice"])
		self.assertEqual(frappe.db.get_value("Rental Contract", doc.name, "status"), "Ending")
		self.assertNotIn(doc.name, renewal.run("2026-12-02")["notice"])  # once per term
		renewal.run("2027-01-01")
		self.assertEqual(frappe.db.get_value("Rental Contract", doc.name, "status"), "Ended")
		self.assertTrue(
			frappe.db.exists("Rental Event Log", {"event": "contract_ended", "reference_name": doc.name})
		)
		self.assertTrue(availability.is_available(unit, "2026-06-01 10:00", "2026-06-02 10:00"))

	def test_auto_renew_with_indexation(self):
		unit = self.unit()
		doc = self.active(
			auto_renew=1,
			renewal_term_months=12,
			indexation_percent=5,
			allocations=[{"allocation_type": "Specific unit", "rental_unit": unit, "rate_override": 100}],
			billing_plan=[{"frequency": "Monthly", "period_amount": 1000}],
		)
		out = renewal.run("2027-01-01")
		self.assertEqual(len(out["renewed"]), 1)
		new = frappe.get_doc("Rental Contract", out["renewed"][0])
		self.assertEqual((new.renewal_of, new.status), (doc.name, "Active"))
		self.assertEqual((str(new.start_date), str(new.end_date)), ("2027-01-01", "2027-12-31"))
		self.assertEqual(flt(new.allocations[0].rate_override), 105)
		self.assertEqual(flt(new.billing_plan[0].period_amount), 1050)
		self.assertEqual(new.rendered_terms, doc.rendered_terms)
		self.assertEqual(frappe.db.get_value("Rental Contract", doc.name, "status"), "Renewed")
		self.assertFalse(availability.is_available(unit, "2027-06-01 10:00", "2027-06-02 10:00"))
		self.assertEqual(renewal.renew(frappe.get_doc("Rental Contract", doc.name)), new.name)  # idempotent

	def test_early_termination_fee_is_billed(self):
		doc = self.active(minimum_term_months=12, early_termination_fee=300)
		event = renewal.terminate(doc, "Moving abroad", "2026-04-01")
		self.assertTrue(event)
		self.assertEqual(frappe.db.get_value("Rental Contract", doc.name, "status"), "Terminated")
		si = invoicing.invoice_contract_events(doc.name, "2026-12-31")
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", si, "net_total")), 300)
		self.assertEqual(frappe.db.get_value("Rental Billable Event", event, "status"), "Invoiced")

	def test_no_fee_after_minimum_term(self):
		doc = self.active(minimum_term_months=3, early_termination_fee=300)
		self.assertIsNone(renewal.terminate(doc, "Done", "2026-06-01"))

	def test_closure_checklist(self):
		doc = self.active()
		checklist = renewal.closure_checklist(doc)
		self.assertEqual(
			set(checklist), {"units_out", "planned_billing_rows", "deposits_held", "pending_charges"}
		)

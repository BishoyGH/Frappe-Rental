"""Rental Contract core (T40): workflow, snapshot unchanged after template edits, amendments."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.compat.erpnext import ensure_setup_complete
from frappe_rental.services import billing, contracts
from frappe_rental.tests.utils import make_customer


def make_template(body="<p>Rent for {{ customer.customer_name }} from {{ contract.start_date }}</p>"):
	clause = frappe.get_doc(
		{
			"doctype": "Rental Clause",
			"title": "Payment",
			"body": "<p>Fee {{ contract.early_termination_fee }}</p>",
			"mandatory": 1,
		}
	).insert()
	return (
		frappe.get_doc(
			{
				"doctype": "Rental Terms Template",
				"template_name": f"T40 {random_string(6)}",
				"body": body,
				"clauses": [{"clause": clause.name}],
			}
		)
		.insert()
		.name
	)


def make_contract(**kw):
	return frappe.get_doc(
		{
			"doctype": "Rental Contract",
			"customer": make_customer(),
			"company": ensure_setup_complete(),
			"start_date": "2026-01-01",
			"end_date": "2026-12-31",
			"early_termination_fee": 300,
			"terms_template": make_template(),
			**kw,
		}
	).insert()


class TestContracts(FrappeTestCase):
	def test_workflow(self):
		doc = make_contract()
		self.assertEqual(doc.status, "Draft")
		with self.assertRaises(frappe.ValidationError):
			contracts.transition(doc, "Active")  # must be signed
		contracts.transition(doc, "In Review")
		contracts.send_for_signature(doc)
		self.assertEqual(doc.status, "Awaiting Signature")
		self.assertIn("Fee 300", doc.rendered_terms)
		erp = contracts.activate(doc, "Jane Customer", countersigned_by="Administrator")
		self.assertEqual(doc.status, "Active")
		self.assertEqual(frappe.db.get_value("Contract", erp, "is_signed"), 1)
		contracts.transition(doc, "Suspended")
		contracts.transition(doc, "Active")
		contracts.terminate(doc, "Customer moved")
		self.assertEqual(doc.status, "Terminated")
		with self.assertRaises(frappe.ValidationError):
			contracts.transition(doc, "Active")

	def test_snapshot_unchanged_after_template_edit(self):
		doc = make_contract()
		contracts.send_for_signature(doc)
		contracts.activate(doc, "Jane")
		snapshot = doc.rendered_terms
		tpl = frappe.get_doc("Rental Terms Template", doc.terms_template)
		tpl.body = "<p>Completely new wording</p>"
		tpl.save()
		clause = frappe.get_doc("Rental Clause", tpl.clauses[0].clause)
		clause.body = "<p>Changed clause</p>"
		clause.save()
		doc.reload()
		self.assertEqual(doc.rendered_terms, snapshot)

	def test_signed_terms_frozen_except_by_amendment(self):
		doc = make_contract()
		contracts.send_for_signature(doc)
		contracts.activate(doc, "Jane")
		doc.early_termination_fee = 999
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		doc.reload()
		before = doc.rendered_terms
		contracts.amend(doc, "Fee renegotiated", "2026-06-01", {"early_termination_fee": 150})
		doc.reload()
		self.assertIn("Fee 150", doc.rendered_terms)
		self.assertEqual(len(doc.amendments), 1)
		self.assertEqual(doc.amendments[0].previous_terms, before)
		with self.assertRaises(frappe.ValidationError):
			contracts.amend(doc, "Bad", changes={"status": "Draft"})

	def test_mandatory_clause_cannot_be_removed(self):
		doc = make_contract()
		other = frappe.get_doc({"doctype": "Rental Clause", "title": "Other", "body": "<p>x</p>"}).insert()
		doc.append("clauses", {"clause": other.name})
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_contract_billing_plan_precedence(self):
		doc = make_contract(billing_plan=[{"frequency": "Quarterly"}])
		booking = frappe._dict(rental_contract=doc.name, billing_plan=[], rental_type=None)
		self.assertEqual(billing.resolve_plan(booking)["frequency"], "Quarterly")
		self.assertEqual(contracts.for_booking(booking), doc.name)

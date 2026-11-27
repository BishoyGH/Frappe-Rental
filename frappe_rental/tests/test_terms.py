"""Clause library and terms templates (T39): merge fields, overrides, RTL, versioning."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.api import terms as api
from frappe_rental.services import terms
from frappe_rental.tests.utils import make_customer


def clause(title, body, **kw):
	return frappe.get_doc({"doctype": "Rental Clause", "title": title, "body": body, **kw}).insert().name


def language(code):
	if not frappe.db.exists("Language", code):
		frappe.get_doc({"doctype": "Language", "language_code": code, "language_name": code}).insert()
	return code


class TestTerms(FrappeTestCase):
	def template(self, clauses, body="<p>Agreement with {{ customer.customer_name }}</p>", **kw):
		return frappe.get_doc(
			{
				"doctype": "Rental Terms Template",
				"template_name": f"T39 {random_string(6)}",
				"body": body,
				"clauses": [{"clause": c} for c in clauses],
				**kw,
			}
		).insert()

	def test_render_merge_fields_in_order(self):
		pay = clause(
			"Payment", "<p>Pay {{ deposit }} deposit by {{ contract.start_date }}</p>", category="Payment"
		)
		use = clause("Use", "<p>Only at {{ contract.site }}</p>", category="Use")
		tpl = self.template([pay, use])
		customer = make_customer()
		out = terms.render(
			tpl.name,
			{
				"customer": frappe.get_doc("Customer", customer),
				"deposit": 500,
				"contract": {"start_date": "2026-12-01", "site": "Cairo"},
			},
		)
		self.assertIn(frappe.db.get_value("Customer", customer, "customer_name"), out["html"])
		self.assertIn("Pay 500 deposit by 2026-12-01", out["html"])
		self.assertEqual([c["title"] for c in out["clauses"]], ["Payment", "Use"])
		self.assertEqual(out["direction"], "ltr")

	def test_overrides_only_on_editable_clauses(self):
		fixed = clause("Fixed", "<p>Original</p>", mandatory=1)
		free = clause("Free", "<p>Default</p>", editable_per_contract=1)
		tpl = self.template([fixed, free])
		out = terms.render(
			tpl.name,
			terms.sample_context(),
			clauses=[{"clause": fixed, "body": "<p>Hacked</p>"}, {"clause": free, "body": "<p>Custom</p>"}],
		)
		self.assertIn("Original", out["html"])
		self.assertNotIn("Hacked", out["html"])
		self.assertIn("Custom", out["html"])
		self.assertEqual(terms.mandatory_missing(tpl.name, [{"clause": free}]), [fixed])

	def test_rtl_language(self):
		tpl = self.template(
			[clause("عقد", "<p>نص {{ customer.customer_name }}</p>")], language=language("ar")
		)
		out = terms.render(tpl.name, terms.sample_context())
		self.assertEqual(out["direction"], "rtl")
		self.assertIn('dir="rtl"', out["html"])

	def test_versioning(self):
		a = clause("A", "<p>a</p>")
		tpl = self.template([a])
		self.assertEqual(tpl.version, 1)
		tpl.is_active = 1
		tpl.save()
		self.assertEqual(tpl.version, 1)  # no text change
		tpl.body = "<p>New intro</p>"
		tpl.save()
		self.assertEqual(tpl.version, 2)
		tpl.append("clauses", {"clause": clause("B", "<p>b</p>")})
		tpl.save()
		self.assertEqual(tpl.version, 3)

	def test_validation(self):
		with self.assertRaises(frappe.ValidationError):
			clause("Bad", "<p>{{ unclosed </p>")
		a = clause("Dup", "<p>x</p>")
		with self.assertRaises(frappe.ValidationError):
			self.template([a, a])

	def test_template_for_fallback(self):
		general = self.template([], language=language("en"))
		self.assertTrue(terms.template_for("Nonexistent Type", "en"))
		self.assertTrue(general.name)

	def test_preview_api(self):
		tpl = self.template([clause("P", "<p>{{ billing_plan.frequency }}</p>")])
		self.assertIn("Monthly", api.preview(tpl.name)["html"])

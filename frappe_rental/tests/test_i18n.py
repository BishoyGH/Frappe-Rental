"""Translations and RTL (T57): SPA strings come from translations/<lang>.csv; Arabic pages are right to left."""

import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_rental.www import rental


class TestI18n(FrappeTestCase):
	def test_arabic_messages_and_direction(self):
		ar = rental.messages("ar")
		self.assertEqual(ar["Confirm booking"], "تأكيد الحجز")
		self.assertEqual(rental.messages("ar-EG")["Total"], ar["Total"])  # falls back to the base language
		self.assertEqual(rental.direction("ar"), "rtl")
		self.assertEqual(rental.direction("ar-EG"), "rtl")
		self.assertEqual(rental.direction("en"), "ltr")

	def test_unknown_or_hostile_language_gives_no_messages(self):
		for lang in ("xx", "../../etc/passwd", "en", "", "a" * 40):
			self.assertEqual(rental.messages(lang) if lang else rental.messages("zz"), {})

	def test_placeholders_survive_translation(self):
		import re

		for source, text in rental.messages("ar").items():
			self.assertEqual(
				sorted(re.findall(r"\{\d\}", source)), sorted(re.findall(r"\{\d\}", text)), source
			)

	def test_portal_boot_carries_messages(self):
		frappe.local.lang = "ar"
		try:
			self.assertIn("Sign in", rental.portal_boot()["messages"])
		finally:
			frappe.local.lang = "en"

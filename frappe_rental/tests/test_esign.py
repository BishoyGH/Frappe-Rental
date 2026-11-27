"""E-signature (T41): typed and drawn signing, OTP, countersign, immutability, reminders."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate, random_string

from frappe_rental.api import contract as api
from frappe_rental.services import esign
from frappe_rental.tests.test_contracts import make_contract

PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


class TestEsign(FrappeTestCase):
	def ready(self, **kw):
		doc = make_contract(**kw)
		esign.request_signature(doc)
		return doc

	def test_typed_sign_then_countersign(self):
		doc = self.ready()
		self.assertTrue(
			frappe.db.exists(
				"Rental Event Log", {"event": "contract_signature_requested", "reference_name": doc.name}
			)
		)
		api.sign(doc.name, "Jane Customer", "Jane Customer")
		doc.reload()
		self.assertEqual((doc.status, doc.signature_type), ("Awaiting Signature", "Typed"))
		signed_on = doc.signed_on
		api.countersign(doc.name)
		doc.reload()
		self.assertEqual(doc.status, "Active")
		self.assertEqual(doc.countersigned_by, "Administrator")
		self.assertEqual(doc.signed_on, signed_on)
		self.assertTrue(frappe.db.get_value("Contract", doc.erpnext_contract, "is_signed"))
		self.assertTrue(
			frappe.db.exists("Rental Event Log", {"event": "contract_signed", "reference_name": doc.name})
		)

	def test_signed_contract_is_immutable(self):
		doc = self.ready()
		esign.customer_sign(doc, "Jane", PNG, "Drawn")
		esign.countersign(doc)
		doc.reload()
		doc.signature = "forged"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		doc.reload()
		with self.assertRaises(frappe.ValidationError):
			esign.customer_sign(doc, "Again", "Again")

	def test_otp_required(self):
		doc = self.ready(require_otp=1)
		with self.assertRaises(frappe.ValidationError):
			esign.customer_sign(doc, "Jane", "Jane")
		with patch.object(esign, "_new_code", return_value="123456"):
			esign.request_otp(doc)
		doc.reload()
		with self.assertRaises(frappe.ValidationError):
			esign.customer_sign(doc, "Jane", "Jane", otp="000000")
		esign.customer_sign(doc, "Jane", "Jane", otp="123456")
		doc.reload()
		self.assertTrue(doc.signed_on)
		self.assertFalse(doc.otp_hash)

	def test_drawn_must_be_image(self):
		doc = self.ready()
		with self.assertRaises(frappe.ValidationError):
			esign.customer_sign(doc, "Jane", "not an image", "Drawn")

	def test_countersign_needs_customer_signature(self):
		doc = self.ready()
		with self.assertRaises(frappe.ValidationError):
			esign.countersign(doc)

	def test_portal_user_permission(self):
		doc = self.ready()
		user = f"t41-{random_string(5)}@example.com"
		frappe.get_doc(
			{"doctype": "User", "email": user, "first_name": "T41", "send_welcome_email": 0}
		).insert(
			ignore_permissions=True  # test fixture
		)
		self.assertFalse(esign.can_sign_for(doc.customer, user))
		contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "T41",
				"user": user,
				"links": [{"link_doctype": "Customer", "link_name": doc.customer}],
			}
		).insert(ignore_permissions=True)  # test fixture
		self.assertTrue(contact.name)
		self.assertTrue(esign.can_sign_for(doc.customer, user))

	def test_reminders_every_three_days(self):
		doc = self.ready()
		frappe.db.set_value(
			"Rental Contract", doc.name, "modified", add_days(nowdate(), -3), update_modified=False
		)
		self.assertGreaterEqual(esign.remind_unsigned(nowdate()), 1)
		self.assertEqual(esign.remind_unsigned(nowdate()), 0)

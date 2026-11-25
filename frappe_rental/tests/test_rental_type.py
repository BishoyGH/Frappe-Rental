import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_rental.services import rental_type as svc


def make_type(name="T06 Gear", fields=None, **kw):
	if frappe.db.exists("Rental Type", name):
		frappe.delete_doc("Rental Type", name, force=True)
	return frappe.get_doc(
		{
			"doctype": "Rental Type",
			"type_name": name,
			"mode": "Resource",
			"time_unit": "Day",
			"custom_fields": fields or [],
			**kw,
		}
	).insert()


class TestRentalType(FrappeTestCase):
	def test_custom_fields_created_on_target_doctype(self):
		# Rental Item arrives in T07; until then use an existing doctype to exercise the sync.
		doc = make_type(
			fields=[
				{
					"applies_to": "Rental Item",
					"label": "Megapixels",
					"fieldname": "t06_megapixels",
					"fieldtype": "Int",
				},
				{"applies_to": "Rental Item", "label": "Lens", "fieldname": "t06_lens", "fieldtype": "Data"},
			]
		)
		touched = svc.sync_custom_fields(doc, targets=("Rental Item",))
		if frappe.db.exists("DocType", "Rental Item"):
			self.assertEqual(sorted(touched), ["t06_lens", "t06_megapixels"])
			self.assertEqual(svc.sync_custom_fields(doc), touched)  # idempotent
		else:
			self.assertEqual(touched, [])

	def test_sync_creates_real_custom_fields(self):
		doc = make_type(
			name="T06 Loc",
			fields=[{"applies_to": "Rental Unit", "label": "X", "fieldname": "t06_x", "fieldtype": "Data"}],
		)
		# Point the row at an existing doctype to prove Custom Field creation and idempotency.
		original = svc.CUSTOM_FIELD_TARGETS
		self.addCleanup(setattr, svc, "CUSTOM_FIELD_TARGETS", original)
		svc.CUSTOM_FIELD_TARGETS = ("Rental Type",)
		doc.custom_fields[0].applies_to = "Rental Type"
		first = svc.sync_custom_fields(doc)
		self.assertEqual(first, ["t06_x"])
		self.assertTrue(frappe.db.exists("Custom Field", {"dt": "Rental Type", "fieldname": "t06_x"}))
		self.assertEqual(svc.sync_custom_fields(doc), ["t06_x"])
		self.assertEqual(frappe.db.count("Custom Field", {"dt": "Rental Type", "fieldname": "t06_x"}), 1)

	def test_bad_fieldname_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_type(
				name="T06 Bad",
				fields=[
					{"applies_to": "Rental Item", "label": "B", "fieldname": "Bad Name", "fieldtype": "Data"}
				],
			)

	def test_presets_install_and_are_idempotent(self):
		svc.install_presets()
		first = frappe.db.count("Rental Type")
		self.assertGreaterEqual(first, 8)
		self.assertEqual(svc.install_presets(), [])
		self.assertEqual(frappe.db.count("Rental Type"), first)

	def test_accounting_dimension(self):
		svc.ensure_accounting_dimension()
		svc.ensure_accounting_dimension()
		self.assertEqual(frappe.db.count("Accounting Dimension", {"document_type": "Rental Type"}), 1)

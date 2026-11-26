import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.api import booking as api
from frappe_rental.compat import erpnext as compat
from frappe_rental.compat.erpnext import ensure_setup_complete
from frappe_rental.services import custom_fields, erpnext_sync
from frappe_rental.services.setup import create_defaults
from frappe_rental.tests.utils import make_customer


class TestErpnextSync(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()

	@classmethod
	def make_fixtures(cls):
		cls.company = ensure_setup_complete()
		create_defaults()
		custom_fields.install()
		currency = frappe.db.get_value("Company", cls.company, "default_currency")
		if not frappe.db.exists("Rental Charge", "T16 Cleaning"):
			frappe.get_doc({"doctype": "Rental Charge", "charge_name": "T16 Cleaning", "amount": 25}).insert()
		if not frappe.db.exists("Rental Rate Card", "T16 Card"):
			frappe.get_doc(
				{
					"doctype": "Rental Rate Card",
					"card_name": "T16 Card",
					"currency": currency,
					"rates": [{"time_unit": "Day", "rate": 100}],
					"charges": [{"charge": "T16 Cleaning"}],
				}
			).insert()
		if not frappe.db.exists("Rental Type", "T16 Device"):
			frappe.get_doc(
				{
					"doctype": "Rental Type",
					"type_name": "T16 Device",
					"mode": "Resource",
					"time_unit": "Day",
					"requires_hold": 0,
				}
			).insert()
		if not frappe.db.exists("Rental Type", "T16 Pool"):
			frappe.get_doc(
				{
					"doctype": "Rental Type",
					"type_name": "T16 Pool",
					"mode": "Resource",
					"time_unit": "Day",
					"requires_hold": 0,
					"identification_mode": "Pooled",
				}
			).insert()
		cls.customer = make_customer()
		cls.tax = cls._tax_template(10)

	@classmethod
	def _tax_template(cls, rate):
		account = frappe.db.get_value(
			"Account", {"company": cls.company, "account_type": "Tax", "is_group": 0}, "name"
		)
		if not account:
			return None
		return (
			frappe.get_doc(
				{
					"doctype": "Sales Taxes and Charges Template",
					"title": f"T16 VAT {random_string(4)}",
					"company": cls.company,
					"taxes": [
						{
							"charge_type": "On Net Total",
							"account_head": account,
							"description": "VAT",
							"rate": rate,
						}
					],
				}
			)
			.insert()
			.name
		)

	def booking(self, taxes=True, submit=True, qty=1, rtype="T16 Device"):
		item = frappe.get_doc(
			{
				"doctype": "Rental Item",
				"item_name": f"T16 {random_string(6)}",
				"rental_type": rtype,
				"rate_card": "T16 Card",
			}
		).insert()
		unit = frappe.get_doc(
			{
				"doctype": "Rental Unit",
				"unit_name": f"T16 {random_string(6)}",
				"rental_item": item.name,
				**({"identification_mode": "Pooled", "quantity_available": 5} if rtype == "T16 Pool" else {}),
			}
		).insert()
		doc = frappe.get_doc(
			{
				"doctype": "Rental Booking",
				"customer": self.customer,
				"rental_type": rtype,
				"company": self.company,
				"from_datetime": "2026-05-01 10:00",
				"to_datetime": "2026-05-04 10:00",
				"taxes_and_charges": self.tax if taxes else None,
				"lines": [{"rental_item": item.name, "rental_unit": unit.name, "qty": qty}],
			}
		).insert()
		if submit:
			doc.submit()
			doc.reload()
		return doc

	def test_confirm_creates_matching_sales_order(self):
		doc = self.booking()
		self.assertTrue(doc.sales_order)
		so = frappe.get_doc("Sales Order", doc.sales_order)
		self.assertEqual(so.docstatus, 1)
		self.assertEqual(so.rental_booking, doc.name)
		self.assertEqual(so.customer, doc.customer)
		self.assertEqual(flt2(so.net_total), flt2(doc.net_total))
		self.assertEqual(flt2(so.total_taxes_and_charges), flt2(doc.total_taxes))
		self.assertEqual(flt2(so.grand_total), flt2(doc.grand_total))
		self.assertEqual(so.items[0].rental_unit, doc.lines[0].rental_unit)
		self.assertEqual(so.items[0].rental_booking_line, doc.lines[0].name)
		self.assertEqual(len(so.items), 2)  # the line and the cleaning charge
		if self.tax:
			self.assertEqual(flt2(doc.total_taxes), flt2(doc.net_total * 0.1))

	def test_sales_order_is_idempotent(self):
		doc = self.booking()
		self.assertEqual(erpnext_sync.make_sales_order(doc), doc.sales_order)
		self.assertEqual(frappe.db.count("Sales Order", {"rental_booking": doc.name}), 1)

	def test_invoice_matches_and_is_idempotent(self):
		doc = self.booking()
		state = api.make_invoice(doc.name)
		si = frappe.get_doc("Sales Invoice", state["sales_invoice"])
		self.assertEqual(si.docstatus, 1)
		self.assertEqual(si.rental_booking, doc.name)
		self.assertEqual(flt2(si.grand_total), flt2(doc.grand_total))
		self.assertEqual(flt2(si.net_total), flt2(doc.net_total))
		self.assertEqual(api.make_invoice(doc.name)["sales_invoice"], si.name)
		self.assertEqual(frappe.db.count("Sales Invoice", {"rental_booking": doc.name}), 1)
		self.assertEqual(frappe.db.get_value("Rental Booking", doc.name, "sales_invoice"), si.name)

	def test_quantity_line_totals_match(self):
		doc = self.booking(taxes=False, submit=False, qty=3, rtype="T16 Pool")
		doc.submit()
		so = frappe.get_doc("Sales Order", doc.sales_order)
		self.assertEqual(flt2(so.grand_total), flt2(doc.grand_total))

	def test_draft_cannot_invoice(self):
		doc = self.booking(submit=False)
		with self.assertRaises(frappe.ValidationError):
			erpnext_sync.make_sales_invoice(doc)
		self.assertIsNone(doc.sales_order)

	def test_auto_invoice_setting(self):
		frappe.db.set_single_value("Rental Settings", "auto_invoice", 1)
		try:
			doc = self.booking()
		finally:
			frappe.db.set_single_value("Rental Settings", "auto_invoice", 0)
		self.assertTrue(doc.sales_invoice)

	def test_cancel_reverses_unpaid(self):
		doc = self.booking()
		si = erpnext_sync.make_sales_invoice(doc)
		so = doc.sales_order
		doc.reload()
		doc.cancel()
		self.assertEqual(frappe.db.get_value("Sales Invoice", si, "docstatus"), 2)
		self.assertEqual(frappe.db.get_value("Sales Order", so, "docstatus"), 2)
		erpnext_sync.reverse(doc)  # twice is safe

	def test_cancel_without_invoice(self):
		doc = self.booking()
		so = doc.sales_order
		doc.cancel()
		self.assertEqual(frappe.db.get_value("Sales Order", so, "docstatus"), 2)

	def test_cancel_paid_invoice_issues_credit_note(self):
		doc = self.booking(taxes=False)
		si = erpnext_sync.make_sales_invoice(doc)
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		pe = get_payment_entry("Sales Invoice", si)
		pe.reference_no = "T16"
		pe.reference_date = pe.posting_date
		pe.insert()
		pe.submit()
		doc.reload()
		doc.cancel()
		self.assertEqual(frappe.db.get_value("Sales Invoice", si, "docstatus"), 1)
		notes = frappe.get_all(
			"Sales Invoice", filters={"return_against": si, "docstatus": 1}, pluck="grand_total"
		)
		self.assertEqual(len(notes), 1)
		self.assertEqual(flt2(notes[0]), -flt2(doc.grand_total))
		erpnext_sync.reverse(doc)
		self.assertEqual(frappe.db.count("Sales Invoice", {"return_against": si}), 1)  # no second note

	def test_charge_item_created_once(self):
		doc = self.booking()
		item = frappe.db.get_value("Rental Charge", "T16 Cleaning", "item")
		self.assertTrue(frappe.db.exists("Item", item))
		self.assertEqual(erpnext_sync._charge_item("T16 Cleaning"), item)
		self.assertTrue(doc.sales_order)

	def test_custom_fields_and_compat(self):
		custom_fields.install()  # idempotent
		for dt, field in (
			("Sales Order", "rental_booking"),
			("Sales Invoice Item", "rental_unit"),
			("Asset", "rental_unit"),
			("Item", "rental_item"),
		):
			self.assertTrue(frappe.get_meta(dt).has_field(field), f"{dt}.{field}")
		self.assertEqual(compat.template_taxes(None), [])
		if self.tax:
			self.assertEqual(compat.template_taxes(self.tax)[0]["rate"], 10)

	def test_api_permission(self):
		doc = self.booking()
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				api.make_invoice(doc.name)
		finally:
			frappe.set_user("Administrator")


def flt2(value):
	return round(float(value or 0), 2)

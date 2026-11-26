"""Damage reports (T28): settlement paths with GL assertions, auto block, Asset Repair link."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, flt, now_datetime, random_string

from frappe_rental.services import damage, deposits
from frappe_rental.tests import test_erpnext_sync as t16
from frappe_rental.tests import test_handover as t27


class TestDamage(FrappeTestCase):
	_tax_template = t16.TestErpnextSync.__dict__["_tax_template"]
	make_fixtures = t16.TestErpnextSync.__dict__["make_fixtures"]
	book = t27.TestHandover.book
	handover = t27.TestHandover.handover

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()
		settings = frappe.get_single("Rental Settings")
		cls.recovery = settings.damage_recovery_account
		cls.liability = settings.deposit_liability_account
		cls.cash = frappe.get_cached_value("Company", cls.company, "default_cash_account")

	def report(self, estimate=200):
		booking, unit = self.book("None")
		self.handover(booking, "Check-out", "2026-07-01 10:00", unit=unit.name)
		back = self.handover(booking, "Return", "2026-07-03 10:00", unit=unit.name, condition="Damaged")
		name = frappe.db.get_value("Rental Damage Report", {"rental_handover": back.name})
		self.assertTrue(name)
		doc = frappe.get_doc("Rental Damage Report", name)
		doc.estimate_amount = estimate
		doc.save()
		return booking, unit, doc

	def gl(self, voucher):
		rows = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": voucher, "is_cancelled": 0},
			fields=["account", "debit", "credit"],
		)
		return {(r.account, flt(r.debit, 2), flt(r.credit, 2)) for r in rows}

	def test_return_raises_report_and_blocks_unit(self):
		booking, unit, doc = self.report()
		self.assertEqual(doc.status, "Estimated")
		self.assertTrue(doc.rental_block)
		self.assertEqual(frappe.db.get_value("Rental Unit", unit.name, "status"), "Maintenance")
		self.assertIsNone(frappe.db.get_value("Rental Block", doc.rental_block, "to_datetime"))
		doc.repaired_on = add_to_date(now_datetime(), hours=1)
		doc.save()
		self.assertTrue(frappe.db.get_value("Rental Block", doc.rental_block, "to_datetime"))
		self.assertEqual(frappe.db.get_value("Rental Unit", unit.name, "status"), "Available")

	def test_settle_from_deposit(self):
		booking, unit, doc = self.report()
		dep = frappe.get_doc(
			{
				"doctype": "Rental Deposit",
				"rental_booking": booking.name,
				"amount_required": 500,
				"liability_account": self.liability,
			}
		).insert()
		deposits.collect(dep.name, 500, cash_account=self.cash)
		damage.approve(doc.name, 150)
		je = damage.settle(doc.name, "Deposit")
		self.assertEqual(self.gl(je), {(self.liability, 150, 0), (self.recovery, 0, 150)})
		self.assertEqual(frappe.db.get_value("Rental Damage Report", doc.name, "status"), "Settled")
		with self.assertRaises(frappe.ValidationError):
			damage.settle(doc.name, "Deposit")  # once only

	def test_settle_by_invoice(self):
		booking, unit, doc = self.report()
		damage.approve(doc.name)
		si = damage.settle(doc.name, "Invoice")
		self.assertTrue(si)
		credits = {(a, c) for a, d, c in self.gl(si) if c}
		self.assertIn((self.recovery, 200), credits)
		event = frappe.db.get_value("Rental Damage Report", doc.name, "billable_event")
		self.assertEqual(frappe.db.get_value("Rental Billable Event", event, "status"), "Invoiced")

	def test_write_off_posts_nothing(self):
		booking, unit, doc = self.report()
		self.assertIsNone(damage.settle(doc.name, "Write-off"))
		self.assertEqual(frappe.db.get_value("Rental Damage Report", doc.name, "status"), "Written Off")
		self.assertFalse(
			frappe.db.exists(
				"Journal Entry",
				{"rental_deposit": ["is", "set"], "user_remark": ["like", f"%{booking.name}%"]},
			)
		)

	def test_settle_needs_approval(self):
		booking, unit, doc = self.report()
		with self.assertRaises(frappe.ValidationError):
			damage.settle(doc.name, "Invoice")

	def test_asset_repair_link(self):
		home = f"T28 Home {random_string(4)}"
		frappe.get_doc({"doctype": "Location", "location_name": home}).insert()
		asset = f"T28-AST-{random_string(5)}"
		frappe.get_doc(
			{
				"doctype": "Asset",
				"name": asset,
				"asset_name": asset,
				"company": self.company,
				"location": home,
				"docstatus": 1,
				"status": "Submitted",
				"item_code": t27.t16_item(),
			}
		).db_insert()
		booking, unit = self.book("Asset", unit_kw={"asset": asset})
		doc = frappe.get_doc(
			{
				"doctype": "Rental Damage Report",
				"rental_booking": booking.name,
				"rental_unit": unit.name,
				"description": "Cracked",
				"block_unit": 0,
			}
		).insert()
		repair = damage.make_asset_repair(doc.name)
		self.assertEqual(frappe.db.get_value("Asset Repair", repair, "asset"), asset)
		self.assertEqual(damage.make_asset_repair(doc.name), repair)

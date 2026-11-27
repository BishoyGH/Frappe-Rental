"""Deposits (T25): GL entries asserted for collection and every settlement path."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, random_string

from frappe_rental.api import deposit as api
from frappe_rental.services import deposits
from frappe_rental.tests import test_erpnext_sync as t16


class TestDeposits(FrappeTestCase):
	_tax_template = t16.TestErpnextSync.__dict__["_tax_template"]
	make_fixtures = t16.TestErpnextSync.__dict__["make_fixtures"]
	booking = t16.TestErpnextSync.booking

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()
		settings = frappe.get_single("Rental Settings")
		cls.liability = settings.deposit_liability_account
		cls.forfeit_income = settings.deposit_forfeiture_income_account
		cls.damage = settings.damage_recovery_account
		cls.cash = frappe.get_cached_value("Company", cls.company, "default_cash_account")
		if not frappe.db.exists("Rental Deposit Rule", "T25 Fixed"):
			frappe.get_doc(
				{
					"doctype": "Rental Deposit Rule",
					"rule_name": "T25 Fixed",
					"deposit_type": "Fixed",
					"amount": 500,
					"refundable": 1,
				}
			).insert()
		frappe.db.set_value("Rental Type", "T16 Device", "deposit_rule", "T25 Fixed")

	@classmethod
	def tearDownClass(cls):
		frappe.db.set_value("Rental Type", "T16 Device", "deposit_rule", None)
		super().tearDownClass()

	def deposit(self):
		doc = self.booking(taxes=False)
		name = deposits.request(doc)
		self.assertTrue(name)
		return name

	def gl(self, je):
		rows = frappe.get_all(
			"GL Entry", filters={"voucher_no": je, "is_cancelled": 0}, fields=["account", "debit", "credit"]
		)
		return {(r.account, flt(r.debit, 2), flt(r.credit, 2)) for r in rows}

	def test_request_is_idempotent_and_emits(self):
		doc = self.booking(taxes=False)
		a = deposits.request(doc)
		self.assertEqual(deposits.request(doc), a)
		self.assertEqual(frappe.db.get_value("Rental Deposit", a, "amount_required"), 500)
		self.assertTrue(
			frappe.db.exists("Rental Event Log", {"event": "deposit_requested", "reference_name": a})
		)

	def test_collect_posts_to_liability(self):
		name = self.deposit()
		je = deposits.collect(name, 500, cash_account=self.cash)
		self.assertEqual(self.gl(je), {(self.cash, 500, 0), (self.liability, 0, 500)})
		dep = frappe.get_doc("Rental Deposit", name)
		self.assertEqual(dep.status, "Held")
		self.assertEqual(flt(dep.balance_held), 500)
		self.assertEqual(flt(frappe.db.get_value("Rental Booking", dep.rental_booking, "deposit_paid")), 500)
		self.assertTrue(
			frappe.db.exists("Rental Event Log", {"event": "deposit_received", "reference_name": name})
		)

	def test_partial_collect(self):
		name = self.deposit()
		deposits.collect(name, 200, cash_account=self.cash)
		self.assertEqual(frappe.db.get_value("Rental Deposit", name, "status"), "Partly Received")

	def test_refund_path(self):
		name = self.deposit()
		deposits.collect(name, 500, cash_account=self.cash)
		je = deposits.refund(name, cash_account=self.cash)
		self.assertEqual(self.gl(je), {(self.liability, 500, 0), (self.cash, 0, 500)})
		self.assertEqual(frappe.db.get_value("Rental Deposit", name, "status"), "Settled")

	def test_apply_to_charges_then_refund_rest(self):
		name = self.deposit()
		deposits.collect(name, 500, cash_account=self.cash)
		je = deposits.apply(name, 120, income_account=self.damage)
		self.assertEqual(self.gl(je), {(self.liability, 120, 0), (self.damage, 0, 120)})
		rest = deposits.refund(name, cash_account=self.cash)
		self.assertEqual(self.gl(rest), {(self.liability, 380, 0), (self.cash, 0, 380)})
		dep = frappe.get_doc("Rental Deposit", name)
		self.assertEqual((dep.status, flt(dep.balance_held), len(dep.entries)), ("Settled", 0, 3))

	def test_apply_to_invoice_reduces_outstanding(self):
		from frappe_rental.services import erpnext_sync

		name = self.deposit()
		deposits.collect(name, 500, cash_account=self.cash)
		booking = frappe.get_doc(
			"Rental Booking", frappe.db.get_value("Rental Deposit", name, "rental_booking")
		)
		si = erpnext_sync.make_sales_invoice(booking)
		before = flt(frappe.db.get_value("Sales Invoice", si, "outstanding_amount"))
		deposits.apply(name, 100, sales_invoice=si)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", si, "outstanding_amount")), before - 100)

	def test_forfeit_path(self):
		name = self.deposit()
		deposits.collect(name, 500, cash_account=self.cash)
		je = deposits.forfeit(name)
		self.assertEqual(self.gl(je), {(self.liability, 500, 0), (self.forfeit_income, 0, 500)})

	def test_cannot_settle_more_than_held(self):
		name = self.deposit()
		deposits.collect(name, 100, cash_account=self.cash)
		with self.assertRaises(frappe.ValidationError):
			deposits.refund(name, 150, cash_account=self.cash)
		with self.assertRaises(frappe.ValidationError):
			deposits.collect(name, 0, cash_account=self.cash)

	def test_api_permission(self):
		name = self.deposit()
		user = f"t25-{random_string(5)}@example.com"
		frappe.get_doc(
			{"doctype": "User", "email": user, "first_name": "T25", "send_welcome_email": 0}
		).insert(
			ignore_permissions=True  # test fixture
		)
		frappe.set_user(user)
		try:
			with self.assertRaises(frappe.PermissionError):
				api.settle(name, "forfeit")
		finally:
			frappe.set_user("Administrator")

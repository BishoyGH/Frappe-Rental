"""Cancellation engine (T26): tier boundaries (pure) and preview equals the posted outcome."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, flt, now_datetime, random_string

from frappe_rental.api import booking as api
from frappe_rental.services import cancellation, erpnext_sync
from frappe_rental.services.cancellation import compute
from frappe_rental.tests import test_erpnext_sync as t16

TIERS = [
	{"hours_before_start": 168, "refund_percent": 100, "fee": 0},
	{"hours_before_start": 48, "refund_percent": 50, "fee": 10},
	{"hours_before_start": 0, "refund_percent": 0, "fee": 0},
]


class TestCompute(FrappeTestCase):
	def test_tier_boundaries(self):
		cases = [
			(200, 100, 0),  # well before: full
			(168, 100, 0),  # exactly at the threshold: that tier
			(167.99, 50, 10),
			(48, 50, 10),
			(47.5, 0, 0),
			(0, 0, 0),
			(-5, None, None),  # after start: no tier met, nothing back
		]
		for hours, pct, fee in cases:
			r = compute(TIERS, hours, total=1000, paid=1000)
			with self.subTest(hours=hours):
				if pct is None:
					self.assertEqual((r["refund"], r["kept"]), (0, 1000))
				else:
					self.assertEqual((r["refund_percent"], r["fee"]), (pct, fee))
					self.assertEqual(r["kept"], min(1000 * (100 - pct) / 100 + fee, 1000))

	def test_money(self):
		r = compute(TIERS, 50, total=1000, paid=1000)
		self.assertEqual((r["kept"], r["refund"], r["amount_due"]), (510, 490, 0))
		r = compute(TIERS, 50, total=1000, paid=200)
		self.assertEqual((r["refund"], r["amount_due"]), (0, 310))

	def test_provider_cancel_refunds_all(self):
		r = compute(TIERS, 1, total=1000, paid=1000, by="provider")
		self.assertEqual((r["refund"], r["kept"], r["fee"]), (1000, 0, 0))

	def test_no_policy_refunds_all(self):
		self.assertEqual(compute(None, 1, total=300, paid=300)["refund"], 300)

	def test_fee_capped_at_total(self):
		self.assertEqual(
			compute([{"hours_before_start": 0, "refund_percent": 100, "fee": 500}], 1, 100, 100)["kept"], 100
		)


class TestCancelBooking(FrappeTestCase):
	_tax_template = t16.TestErpnextSync.__dict__["_tax_template"]
	make_fixtures = t16.TestErpnextSync.__dict__["make_fixtures"]

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()
		if not frappe.db.exists("Rental Cancellation Policy", "T26 Policy"):
			frappe.get_doc(
				{"doctype": "Rental Cancellation Policy", "policy_name": "T26 Policy", "tiers": TIERS}
			).insert()
		if not frappe.db.exists("Rental Type", "T26 Device"):
			frappe.get_doc(
				{
					"doctype": "Rental Type",
					"type_name": "T26 Device",
					"mode": "Resource",
					"time_unit": "Day",
					"requires_hold": 0,
					"cancellation_policy": "T26 Policy",
				}
			).insert()

	def booking(self, days_ahead):
		item = frappe.get_doc(
			{
				"doctype": "Rental Item",
				"item_name": f"T26 {random_string(6)}",
				"rental_type": "T26 Device",
				"rate_card": "T16 Card",
			}
		).insert()
		unit = frappe.get_doc(
			{"doctype": "Rental Unit", "unit_name": f"T26 {random_string(6)}", "rental_item": item.name}
		).insert()
		start = add_to_date(now_datetime(), days=days_ahead)
		doc = frappe.get_doc(
			{
				"doctype": "Rental Booking",
				"customer": self.customer,
				"rental_type": "T26 Device",
				"company": self.company,
				"from_datetime": start,
				"to_datetime": add_to_date(start, days=2),
				"lines": [{"rental_item": item.name, "rental_unit": unit.name, "qty": 1}],
			}
		).insert()
		doc.submit()
		doc.reload()
		return doc

	def pay(self, si):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		pe = get_payment_entry("Sales Invoice", si)
		pe.reference_no, pe.reference_date = "T26", pe.posting_date
		pe.insert()
		pe.submit()

	def test_preview_equals_actual_mid_tier_paid(self):
		doc = self.booking(days_ahead=3)  # 72 h: 50% back less a 10 fee
		self.pay(erpnext_sync.make_sales_invoice(doc))
		doc.reload()
		before = api.cancellation_preview(doc.name)
		self.assertEqual((before["refund_percent"], before["fee"]), (50, 10))
		result = cancellation.cancel(doc)
		self.assertEqual(result["refund"], before["refund"])
		notes = frappe.get_all(
			"Sales Invoice",
			filters={"rental_booking": doc.name, "is_return": 1, "docstatus": 1},
			pluck="name",
		)
		credited = -sum(flt(frappe.db.get_value("Sales Invoice", n, "grand_total")) for n in notes)
		self.assertEqual(flt(credited, 2), flt(result["refund"], 2))
		refs = frappe.get_all(
			"Payment Entry Reference", filters={"reference_name": ["in", notes]}, pluck="parent"
		)
		paid_back = sum(
			flt(frappe.db.get_value("Payment Entry", p, "paid_amount"))
			for p in set(refs)
			if frappe.db.get_value("Payment Entry", p, "docstatus") == 1
		)
		self.assertEqual(flt(paid_back, 2), flt(result["refund"], 2))

	def test_unpaid_late_cancel_bills_fee(self):
		doc = self.booking(days_ahead=1)  # 24 h: 0% back, all kept
		result = api.cancel_with_policy(doc.name)["cancellation"]
		self.assertEqual(result["refund"], 0)
		fees = frappe.get_all(
			"Sales Invoice",
			filters={"rental_booking": doc.name, "docstatus": 1, "is_return": 0},
			fields=["grand_total"],
		)
		self.assertEqual(flt(sum(f.grand_total for f in fees), 2), flt(result["kept"], 2))

	def test_early_cancel_unpaid_cancels_invoice(self):
		doc = self.booking(days_ahead=10)
		si = erpnext_sync.make_sales_invoice(doc)
		api.cancel_with_policy(doc.name)
		self.assertEqual(frappe.db.get_value("Sales Invoice", si, "docstatus"), 2)
		self.assertFalse(frappe.db.exists("Sales Invoice", {"rental_booking": doc.name, "docstatus": 1}))

	def test_provider_cancel_full_refund(self):
		doc = self.booking(days_ahead=1)
		si = erpnext_sync.make_sales_invoice(doc)
		self.pay(si)
		doc.reload()
		result = api.cancel_with_policy(doc.name, by="provider")["cancellation"]
		self.assertEqual(flt(result["refund"], 2), flt(doc.grand_total, 2))

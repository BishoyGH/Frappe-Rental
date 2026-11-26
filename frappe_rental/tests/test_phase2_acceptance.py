"""Phase 2 acceptance (T32): full lifecycles with GL checks, on both versions.

1. Quarterly device: a year-long rental billed in four quarterly invoices that add up to the booking.
2. Hotel stay: three nights, invoiced, checked in and out.
3. Damage with deposit refund: deposit collected, damage taken from it, the rest refunded.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, random_string

from frappe_rental.api import booking as booking_api
from frappe_rental.services import damage, demo, deposits, erpnext_sync, invoicing, lifecycle


def ensure_fiscal_year(year: int, company: str) -> None:
	if frappe.db.get_value("Fiscal Year", {"year_start_date": f"{year}-01-01"}):
		return
	fy = frappe.get_doc(
		{
			"doctype": "Fiscal Year",
			"year": str(year),
			"year_start_date": f"{year}-01-01",
			"year_end_date": f"{year}-12-31",
		}
	)
	fy.append("companies", {"company": company})
	fy.insert(ignore_if_duplicate=True)


class TestPhase2Acceptance(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.data = demo.make_demo()
		cls.company = frappe.db.get_single_value(
			"Rental Settings", "default_company"
		) or frappe.defaults.get_global_default("company")
		cls.customer = cls.data["customers"][0]
		cls.currency = frappe.db.get_value("Company", cls.company, "default_currency")
		for y in (2027, 2028):
			ensure_fiscal_year(y, cls.company)

	def make_type(self, time_unit="Day", rate=100, **flags):
		tag = random_string(5)
		rtype = frappe.get_doc(
			{
				"doctype": "Rental Type",
				"type_name": f"T32 {tag}",
				"mode": "Resource",
				"time_unit": time_unit,
				**flags,
			}
		).insert()
		card = frappe.get_doc(
			{
				"doctype": "Rental Rate Card",
				"card_name": f"T32 {tag}",
				"currency": self.currency,
				"rates": [{"time_unit": "Day" if time_unit == "Night" else time_unit, "rate": rate}],
			}
		).insert()
		item = frappe.get_doc(
			{
				"doctype": "Rental Item",
				"item_name": f"T32 {tag}",
				"rental_type": rtype.name,
				"rate_card": card.name,
			}
		).insert()
		unit = frappe.get_doc(
			{"doctype": "Rental Unit", "unit_name": f"T32 {tag}", "rental_item": item.name}
		).insert()
		return rtype.name, item.name, unit.name

	def booking(self, rtype, item, start, end, **extra):
		return frappe.get_doc(
			{
				"doctype": "Rental Booking",
				"customer": self.customer,
				"rental_type": rtype,
				"company": self.company,
				"from_datetime": start,
				"to_datetime": end,
				"lines": [{"rental_item": item}],
				**extra,
			}
		).insert()

	def gl(self, voucher):
		return frappe.get_all(
			"GL Entry",
			filters={"voucher_no": voucher, "is_cancelled": 0},
			fields=["account", "debit", "credit", "party"],
		)

	def assert_balanced(self, voucher):
		rows = self.gl(voucher)
		self.assertTrue(rows, voucher)
		self.assertAlmostEqual(sum(flt(r.debit) for r in rows), sum(flt(r.credit) for r in rows), places=2)

	def test_quarterly_device(self):
		rtype, item, _unit = self.make_type("Month", 300)
		doc = self.booking(
			rtype,
			item,
			"2027-01-01 00:00",
			"2028-01-01 00:00",
			billing_plan=[
				{"frequency": "Quarterly", "alignment": "Calendar period start", "timing": "In advance"}
			],
		)
		lifecycle.place_hold(doc)
		doc.submit()
		doc.reload()
		self.assertEqual(len(doc.billing_schedule), 4)
		self.assertAlmostEqual(sum(flt(r.amount) for r in doc.billing_schedule), flt(doc.net_total), places=2)
		invoicing.run_due_invoices("2028-01-02")
		invoices = frappe.get_all(
			"Sales Invoice", filters={"rental_booking": doc.name, "docstatus": ["<", 2]}, pluck="name"
		)
		self.assertEqual(len(invoices), 4)
		self.assertAlmostEqual(
			sum(flt(frappe.db.get_value("Sales Invoice", i, "net_total")) for i in invoices),
			flt(doc.net_total),
			places=2,
		)
		invoicing.run_due_invoices("2028-01-02")  # idempotent
		self.assertEqual(
			len(frappe.get_all("Sales Invoice", filters={"rental_booking": doc.name, "docstatus": ["<", 2]})),
			4,
		)

	def test_hotel_stay(self):
		rtype, item, unit = self.make_type("Night", 80)
		doc = self.booking(rtype, item, "2027-04-10 15:00", "2027-04-13 11:00")
		self.assertAlmostEqual(flt(doc.net_total), 240, places=2)
		lifecycle.place_hold(doc)
		doc.submit()
		invoice = erpnext_sync.make_sales_invoice(doc, submit=True)
		self.assert_balanced(invoice)
		booking_api.checkout(doc.name)
		booking_api.checkin(doc.name)
		self.assertEqual(frappe.db.get_value("Rental Booking", doc.name, "status"), "Returned")
		self.assertEqual(frappe.db.get_value("Rental Unit", unit, "status"), "Available")

	def test_damage_with_deposit_refund(self):
		rule = frappe.get_doc(
			{
				"doctype": "Rental Deposit Rule",
				"rule_name": f"T32 {random_string(5)}",
				"deposit_type": "Fixed",
				"amount": 500,
				"refundable": 1,
			}
		).insert()
		rtype, item, unit = self.make_type("Day", 100, requires_deposit=1, deposit_rule=rule.name)
		doc = self.booking(rtype, item, "2027-05-03 10:00", "2027-05-05 10:00")
		self.assertAlmostEqual(flt(doc.deposit_required), 500, places=2)
		lifecycle.place_hold(doc)
		dep = frappe.db.get_value("Rental Deposit", {"rental_booking": doc.name})
		cash = frappe.get_cached_value("Company", self.company, "default_cash_account")
		collected = deposits.collect(dep, 500, cash_account=cash)
		doc.reload()
		doc.submit()
		booking_api.checkout(doc.name)
		booking_api.checkin(doc.name, lines=[{"rental_unit": unit, "condition": "Damaged"}])
		report = frappe.db.get_value("Rental Damage Report", {"rental_booking": doc.name})
		damage.approve(report, 150)
		applied = damage.settle(report, "Deposit")
		refunded = deposits.refund(dep, cash_account=cash)
		d = frappe.get_doc("Rental Deposit", dep)
		self.assertAlmostEqual(flt(d.amount_applied), 150, places=2)
		self.assertAlmostEqual(flt(d.amount_refunded), 350, places=2)
		self.assertAlmostEqual(flt(d.balance_held), 0, places=2)
		liability = d.liability_account
		net = 0
		for je in (collected, applied, refunded):
			self.assert_balanced(je)
			net += sum(flt(r.credit) - flt(r.debit) for r in self.gl(je) if r.account == liability)
		self.assertAlmostEqual(net, 0, places=2)

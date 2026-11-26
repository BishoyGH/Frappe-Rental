import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.api.booking import quote as api_quote
from frappe_rental.compat.erpnext import ensure_setup_complete
from frappe_rental.services import booking as svc
from frappe_rental.services import lifecycle
from frappe_rental.services.setup import create_defaults
from frappe_rental.tests.utils import make_customer


def get_or_make(doctype, name, **values):
	key = frappe.get_meta(doctype).autoname.split(":")[-1]
	if not frappe.db.exists(doctype, name):
		frappe.get_doc({"doctype": doctype, key: name, **values}).insert()
	return name


class TestRentalBooking(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = ensure_setup_complete()
		create_defaults()
		currency = frappe.db.get_value("Company", cls.company, "default_currency")
		get_or_make("Rental Charge", "T12 Cleaning", amount=20)
		get_or_make(
			"Rental Rate Card",
			"T12 Card",
			currency=currency,
			rates=[
				{"time_unit": "Day", "rate": 100, "max_units": 7},
				{"time_unit": "Day", "rate": 80, "min_units": 7},
			],
			charges=[{"charge": "T12 Cleaning"}],
		)
		get_or_make("Rental Deposit Rule", "T12 Deposit", percent=10)
		get_or_make(
			"Rental Type",
			"T12 Device",
			mode="Resource",
			time_unit="Day",
			min_duration=1,
			max_duration=30,
			deposit_rule="T12 Deposit",
		)
		get_or_make(
			"Rental Type", "T12 Tent", mode="Resource", time_unit="Night", identification_mode="Pooled"
		)
		cls.item = (
			frappe.get_doc(
				{
					"doctype": "Rental Item",
					"item_name": "T12 Camera",
					"rental_type": "T12 Device",
					"rate_card": "T12 Card",
				}
			)
			.insert()
			.name
		)
		cls.other_item = (
			frappe.get_doc(
				{
					"doctype": "Rental Item",
					"item_name": "T12 Lens",
					"rental_type": "T12 Device",
					"rate_card": "T12 Card",
				}
			)
			.insert()
			.name
		)
		cls.tent = (
			frappe.get_doc(
				{
					"doctype": "Rental Item",
					"item_name": "T12 Tent",
					"rental_type": "T12 Tent",
					"rate_card": "T12 Card",
				}
			)
			.insert()
			.name
		)
		cls.unit = (
			frappe.get_doc({"doctype": "Rental Unit", "unit_name": "T12 Cam 1", "rental_item": cls.item})
			.insert()
			.name
		)
		cls.customer = make_customer()

	def booking(self, lines=None, **kw):
		values = {
			"doctype": "Rental Booking",
			"customer": self.customer,
			"rental_type": "T12 Device",
			"from_datetime": "2026-03-02 10:00:00",
			"to_datetime": "2026-03-05 10:00:00",
			"lines": lines or [{"rental_item": self.item, "rental_unit": self.unit}],
			**kw,
		}
		return frappe.get_doc(values)

	def test_draft_prices_lines_charges_deposit(self):
		doc = self.booking().insert()
		self.assertEqual(doc.status, "Draft")
		self.assertEqual(doc.company, self.company)
		line = doc.lines[0]
		self.assertEqual((line.time_unit, line.units, line.rate, line.amount), ("Day", 3, 100, 300))
		self.assertIn("row 1", line.applied_rule)
		self.assertEqual([(c.charge, c.amount) for c in doc.charges], [("T12 Cleaning", 20)])
		self.assertEqual((doc.net_total, doc.grand_total), (320, 320))
		self.assertEqual(doc.deposit_required, 32)

	def test_reprice_on_change_keeps_manual_charge(self):
		doc = self.booking().insert()
		doc.append("charges", {"description": "Delivery", "amount": 15, "is_manual": 1})
		doc.to_datetime = "2026-03-10 10:00:00"  # 8 days: tier rate 80
		doc.save()
		self.assertEqual(doc.lines[0].amount, 640)
		self.assertEqual(sorted(c.amount for c in doc.charges), [15, 20])
		self.assertEqual(doc.net_total, 675)
		doc.save()
		self.assertEqual(len(doc.charges), 2)  # idempotent

	def test_line_discount_and_tax(self):
		template = self._tax_template(10)
		doc = self.booking(
			[{"rental_item": self.item, "discount_pct": 50}], taxes_and_charges=template
		).insert()
		self.assertEqual(doc.lines[0].amount, 150)
		self.assertEqual(doc.net_total, 170)
		self.assertEqual(doc.total_taxes, 17)
		self.assertEqual(doc.grand_total, 187)

	def test_coupon_percent(self):
		rule = f"T12-PR-{random_string(5)}"
		frappe.get_doc(
			{
				"doctype": "Pricing Rule",
				"name": rule,
				"title": rule,
				"rate_or_discount": "Discount Percentage",
				"discount_percentage": 20,
				"disable": 0,
			}
		).db_insert()
		coupon = f"T12-CPN-{random_string(5)}"
		frappe.get_doc(
			{
				"doctype": "Coupon Code",
				"name": coupon,
				"coupon_name": coupon,
				"coupon_code": coupon,
				"pricing_rule": rule,
			}
		).db_insert()
		self.assertEqual(svc.coupon_discount_pct(coupon), 20)
		self.assertEqual(svc.coupon_discount_pct(None), 0)
		doc = self.booking(coupon_code=coupon).insert()
		self.assertEqual(doc.lines[0].amount, 240)

	def test_type_rules(self):
		cases = {
			"end before start": dict(to_datetime="2026-03-01 10:00:00"),
			"below minimum duration": dict(to_datetime="2026-03-02 15:00:00"),
			"above maximum duration": dict(to_datetime="2026-05-02 10:00:00"),
			"item of another type": dict(lines=[{"rental_item": self.tent}]),
			"unit of another item": dict(lines=[{"rental_item": self.other_item, "rental_unit": self.unit}]),
			"qty not allowed": dict(lines=[{"rental_item": self.item, "qty": 2}]),
			"line outside period": dict(
				lines=[{"rental_item": self.item, "to_datetime": "2026-03-09 10:00:00"}]
			),
		}
		for name, kw in cases.items():
			lines = kw.pop("lines", None)
			with self.subTest(name), self.assertRaises(frappe.ValidationError):
				self.booking(lines, **kw).insert()

	def test_pooled_type_allows_qty_and_night_unit(self):
		doc = self.booking([{"rental_item": self.tent, "qty": 4}], rental_type="T12 Tent").insert()
		self.assertEqual(doc.lines[0].amount, 1200)

	def test_item_without_rate_card(self):
		bare = (
			frappe.get_doc({"doctype": "Rental Item", "item_name": "T12 Bare", "rental_type": "T12 Device"})
			.insert()
			.name
		)
		with self.assertRaises(frappe.ValidationError):
			self.booking([{"rental_item": bare}]).insert()

	def test_api_quote_does_not_save(self):
		before = frappe.db.count("Rental Booking")
		data = self.booking().as_dict()
		result = api_quote(frappe.as_json(data))
		self.assertEqual(result["grand_total"], 320)
		self.assertEqual(result["lines"][0]["units"], 3)
		self.assertEqual(frappe.db.count("Rental Booking"), before)
		with self.assertRaises(frappe.ValidationError):
			api_quote({"customer": self.customer})
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				api_quote(data)
		finally:
			frappe.set_user("Administrator")

	def test_submit(self):
		doc = self.booking().insert()
		lifecycle.place_hold(doc)  # Rental Types use the hold step by default
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

	def _tax_template(self, rate):
		title = f"T12 VAT {random_string(4)}"
		account = frappe.db.get_value(
			"Account", {"company": self.company, "account_type": "Tax", "is_group": 0}, "name"
		)
		if not account:
			self.skipTest("no tax account")
		return (
			frappe.get_doc(
				{
					"doctype": "Sales Taxes and Charges Template",
					"title": title,
					"company": self.company,
					"taxes": [
						{
							"charge_type": "On Net Total",
							"account_head": account,
							"rate": rate,
							"description": "VAT",
						}
					],
				}
			)
			.insert()
			.name
		)

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.compat.erpnext import ensure_setup_complete
from frappe_rental.services.rate_card import find_overlap
from frappe_rental.services.setup import create_defaults


def row(idx, **kw):
	return {"idx": idx, "time_unit": "Day", "priority": 0, "weekday_mask": "1111111", **kw}


class TestFindOverlap(FrappeTestCase):
	def test_cases(self):
		cases = [
			("same everything", [row(1), row(2)], (1, 2)),
			("different priority", [row(1), row(2, priority=1)], None),
			("different unit", [row(1), row(2, time_unit="Week")], None),
			("disjoint weekdays", [row(1, weekday_mask="1111100"), row(2, weekday_mask="0000011")], None),
			("shared weekday", [row(1, weekday_mask="1111100"), row(2, weekday_mask="0000111")], (1, 2)),
			("disjoint dates", [row(1, valid_to="2026-06-30"), row(2, valid_from="2026-07-01")], None),
			("touching dates", [row(1, valid_to="2026-07-01"), row(2, valid_from="2026-07-01")], (1, 2)),
			("tiers back to back", [row(1, max_units=7), row(2, min_units=7)], None),
			("tiers overlap", [row(1, max_units=8), row(2, min_units=7)], (1, 2)),
			("open tier vs bounded", [row(1, min_units=30), row(2, min_units=7, max_units=30)], None),
			("different season", [row(1, season="Summer"), row(2, season="Winter")], None),
			("season vs none", [row(1, season="Summer"), row(2)], None),
			("customer group", [row(1, customer_group="VIP"), row(2, customer_group="VIP")], (1, 2)),
			("unit specific", [row(1, rental_unit="RU-1"), row(2)], None),
			("third row clashes", [row(1), row(2, priority=1), row(3, priority=1)], (2, 3)),
		]
		for name, rows, expected in cases:
			with self.subTest(name):
				self.assertEqual(find_overlap(rows), expected)


class TestRateCardDoctypes(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = ensure_setup_complete()
		create_defaults()
		cls.currency = frappe.db.get_value("Company", cls.company, "default_currency")

	def card(self, rates, **kw):
		return frappe.get_doc(
			{
				"doctype": "Rental Rate Card",
				"card_name": f"T10 {random_string(6)}",
				"currency": self.currency,
				"rates": rates,
				**kw,
			}
		)

	def test_rate_card_crud_and_overlap(self):
		doc = self.card(
			[
				{"time_unit": "Day", "rate": 100, "max_units": 7},
				{"time_unit": "Day", "rate": 80, "min_units": 7},
			]
		).insert()
		doc.append("rates", {"time_unit": "Day", "rate": 90, "min_units": 7})
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		doc.reload()
		doc.rates[1].priority = 1
		doc.append("rates", {"time_unit": "Week", "rate": 500})
		doc.save()
		self.assertEqual(len(frappe.get_doc("Rental Rate Card", doc.name).rates), 2 + 1)
		frappe.delete_doc("Rental Rate Card", doc.name)

	def test_rate_row_validation(self):
		bad = [
			{"time_unit": "Day", "rate": 10, "weekday_mask": "11111"},
			{"time_unit": "Day", "rate": 10, "weekday_mask": "0000000"},
			{"time_unit": "Day", "rate": -1},
			{"time_unit": "Day", "rate": 10, "min_units": 5, "max_units": 5},
			{"time_unit": "Day", "rate": 10, "valid_from": "2026-02-01", "valid_to": "2026-01-01"},
		]
		for rate in bad:
			with self.subTest(rate=rate), self.assertRaises(frappe.ValidationError):
				self.card([rate]).insert()
		with self.assertRaises(frappe.ValidationError):
			self.card([], rounding_mode="Minimum charge").insert()

	def test_season(self):
		name = f"T10 Summer {random_string(4)}"
		frappe.get_doc(
			{
				"doctype": "Rental Season",
				"season_name": name,
				"from_date": "2026-06-01",
				"to_date": "2026-08-31",
			}
		).insert()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Rental Season",
					"season_name": name + "x",
					"from_date": "2026-09-01",
					"to_date": "2026-08-31",
				}
			).insert()

	def test_charge(self):
		fixed = frappe.get_doc(
			{"doctype": "Rental Charge", "charge_name": f"T10 Cleaning {random_string(4)}", "amount": 25}
		).insert()
		self.card([{"time_unit": "Day", "rate": 10}], charges=[{"charge": fixed.name}]).insert()
		with self.assertRaises(frappe.ValidationError):
			self.card([], charges=[{"charge": fixed.name}, {"charge": fixed.name}]).insert()
		for kw in ({"amount": 0}, {"charge_type": "Percent", "percent": 150}):
			with self.subTest(kw=kw), self.assertRaises(frappe.ValidationError):
				frappe.get_doc(
					{"doctype": "Rental Charge", "charge_name": f"T10 Bad {random_string(4)}", **kw}
				).insert()

	def test_deposit_rule(self):
		liability = frappe.db.get_single_value("Rental Settings", "deposit_liability_account")
		frappe.get_doc(
			{
				"doctype": "Rental Deposit Rule",
				"rule_name": f"T10 Dep {random_string(4)}",
				"percent": 20,
				"liability_account": liability,
			}
		).insert()
		income = frappe.db.get_single_value("Rental Settings", "rental_income_account")
		for kw in (
			{"percent": 0},
			{"deposit_type": "Fixed", "amount": 0},
			{"percent": 10, "liability_account": income},
		):
			with self.subTest(kw=kw), self.assertRaises(frappe.ValidationError):
				frappe.get_doc(
					{"doctype": "Rental Deposit Rule", "rule_name": f"T10 Bad {random_string(4)}", **kw}
				).insert()

	def test_cancellation_policy(self):
		doc = frappe.get_doc(
			{
				"doctype": "Rental Cancellation Policy",
				"policy_name": f"T10 Flexible {random_string(4)}",
				"tiers": [
					{"hours_before_start": 24, "refund_percent": 50},
					{"hours_before_start": 72, "refund_percent": 100},
				],
			}
		).insert()
		self.assertEqual([t.hours_before_start for t in doc.tiers], [72, 24])  # sorted longest notice first
		bad = [
			[
				{"hours_before_start": 24, "refund_percent": 50},
				{"hours_before_start": 24, "refund_percent": 10},
			],
			[{"hours_before_start": 24, "refund_percent": 120}],
			[{"hours_before_start": -1, "refund_percent": 10}],
		]
		for tiers in bad:
			with self.subTest(tiers=tiers), self.assertRaises(frappe.ValidationError):
				frappe.get_doc(
					{
						"doctype": "Rental Cancellation Policy",
						"policy_name": f"T10 Bad {random_string(4)}",
						"tiers": tiers,
					}
				).insert()

	def test_links_on_type_and_item(self):
		self.assertTrue(frappe.get_meta("Rental Type").has_field("deposit_rule"))
		self.assertTrue(frappe.get_meta("Rental Type").has_field("cancellation_policy"))
		self.assertTrue(frappe.get_meta("Rental Item").has_field("rate_card"))

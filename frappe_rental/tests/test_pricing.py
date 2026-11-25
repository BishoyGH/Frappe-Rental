"""Table-driven tests for the pure pricing engine (T11). No database access."""

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from frappe_rental.services.pricing import PricingError, billable_units, quote, quote_with_hooks


def R(idx, time_unit, rate, **kw):
	return {"idx": idx, "time_unit": time_unit, "rate": rate, **kw}


DAY = R(1, "Day", 100)
HOUR = R(2, "Hour", 10)
WEEK = R(3, "Week", 500)
MONTH = R(4, "Month", 1500)
BASE_CARD = {"currency": "USD", "rounding_mode": "Per started unit", "rates": [DAY]}


def req(start, end, **kw):
	return {"from_datetime": start, "to_datetime": end, **kw}


# (name, request, card overrides, expected subset)
CASES = [
	# Billing units, per started unit
	("one day", req("2026-03-02 10:00", "2026-03-03 10:00"), {}, {"units": 1, "base_amount": 100}),
	(
		"day and a minute starts a second day",
		req("2026-03-02 10:00", "2026-03-03 10:01"),
		{},
		{"units": 2, "base_amount": 200},
	),
	("three days", req("2026-03-02", "2026-03-05"), {}, {"units": 3, "grand_total": 300}),
	(
		"hours",
		req("2026-03-02 10:00", "2026-03-02 13:30"),
		{"rates": [HOUR]},
		{"units": 4, "base_amount": 40},
	),
	(
		"minutes",
		req("2026-03-02 10:00", "2026-03-02 10:45"),
		{"rates": [R(1, "Minute", 0.5)]},
		{"units": 45, "base_amount": 22.5},
	),
	("weeks", req("2026-03-02", "2026-03-12"), {"rates": [WEEK]}, {"units": 2, "base_amount": 1000}),
	("one month", req("2026-01-15", "2026-02-15"), {"rates": [MONTH]}, {"units": 1, "base_amount": 1500}),
	("month and a day", req("2026-01-15", "2026-02-16"), {"rates": [MONTH]}, {"units": 2}),
	(
		"year",
		req("2026-01-01", "2027-01-01"),
		{"rates": [R(1, "Year", 12000)]},
		{"units": 1, "base_amount": 12000},
	),
	(
		"per use",
		req("2026-03-02 10:00", "2026-03-02 11:00", uses=3),
		{"rates": [R(1, "Use", 15)]},
		{"units": 3, "base_amount": 45},
	),
	("qty multiplies", req("2026-03-02", "2026-03-04", qty=3), {}, {"base_amount": 600}),
	# Rounding modes
	(
		"pro-rata day",
		req("2026-03-02 00:00", "2026-03-03 12:00"),
		{"rounding_mode": "Pro-rata"},
		{"units": 1.5, "base_amount": 150},
	),
	(
		"pro-rata hours",
		req("2026-03-02 10:00", "2026-03-02 10:20"),
		{"rates": [HOUR], "rounding_mode": "Pro-rata"},
		{"base_amount": 3.33},
	),
	(
		"minimum charge applies",
		req("2026-03-02 10:00", "2026-03-02 11:00"),
		{"rates": [HOUR], "rounding_mode": "Minimum charge", "minimum_charge": 50},
		{"base_amount": 50},
	),
	(
		"minimum charge exceeded",
		req("2026-03-02 10:00", "2026-03-02 18:00"),
		{"rates": [HOUR], "rounding_mode": "Minimum charge", "minimum_charge": 50},
		{"base_amount": 80},
	),
	# Month end and pro-rata months
	("jan 31 to feb 28 is one month", req("2026-01-31", "2026-02-28"), {"rates": [MONTH]}, {"units": 1}),
	(
		"half of february pro-rata",
		req("2026-02-01", "2026-02-15"),
		{"rates": [MONTH], "rounding_mode": "Pro-rata"},
		{"units": 0.5, "base_amount": 750},
	),
	(
		"leap february month",
		req("2028-02-01", "2028-03-01"),
		{"rates": [MONTH], "rounding_mode": "Pro-rata"},
		{"units": 1},
	),
	(
		"month and half pro-rata",
		req("2026-04-01", "2026-05-16 12:00"),
		{"rates": [MONTH], "rounding_mode": "Pro-rata"},
		{"units": 1.5},
	),
	("year end crossing", req("2026-12-15", "2027-01-15"), {"rates": [MONTH]}, {"units": 1}),
	# DST (Europe/Berlin: 2026-03-29 spring forward, 2026-10-25 fall back)
	(
		"night across spring DST is one day",
		req("2026-03-28 13:00", "2026-03-29 12:00", timezone="Europe/Berlin"),
		{},
		{"units": 1},
	),
	(
		"night across fall DST is one day",
		req("2026-10-24 12:00", "2026-10-25 13:00", timezone="Europe/Berlin"),
		{},
		{"units": 1},
	),
	(
		"hours across spring DST count real time",
		req("2026-03-28 23:00", "2026-03-29 23:00", timezone="Europe/Berlin"),
		{"rates": [HOUR]},
		{"units": 24},
	),
	(
		"local midnight to midnight on fall DST",
		req("2026-10-24 22:00", "2026-10-25 23:00", timezone="Europe/Berlin"),
		{"rates": [HOUR]},
		{"units": 25},
	),
	# Duration breaks (tiers)
	(
		"short stay base rate",
		req("2026-03-02", "2026-03-05"),
		{"rates": [R(1, "Day", 100, max_units=7), R(2, "Day", 90, min_units=7)]},
		{"rate": 100, "base_amount": 300},
	),
	(
		"seven nights tier",
		req("2026-03-02", "2026-03-09"),
		{"rates": [R(1, "Day", 100, max_units=7), R(2, "Day", 90, min_units=7)]},
		{"rate": 90, "base_amount": 630},
	),
	(
		"flat monthly beats daily by priority",
		req("2026-03-01", "2026-04-01"),
		{"rates": [R(1, "Day", 100), R(2, "Month", 2000, priority=1)]},
		{"time_unit": "Month", "base_amount": 2000},
	),
	(
		"same priority picks cheaper unit",
		req("2026-03-02", "2026-03-09"),
		{"rates": [DAY, WEEK]},
		{"time_unit": "Week", "base_amount": 500},
	),
	# Seasons and weekdays (2026-03-02 is a Monday, 2026-03-07 a Saturday)
	(
		"season rate in season",
		req("2026-07-10", "2026-07-11", seasons={"Summer": ("2026-06-01", "2026-08-31")}),
		{"rates": [DAY, R(2, "Day", 150, season="Summer")]},
		{"rate": 150},
	),
	(
		"season rate out of season",
		req("2026-09-10", "2026-09-11", seasons={"Summer": ("2026-06-01", "2026-08-31")}),
		{"rates": [DAY, R(2, "Day", 150, season="Summer")]},
		{"rate": 100},
	),
	(
		"weekend rate on saturday",
		req("2026-03-07", "2026-03-08"),
		{"rates": [R(1, "Day", 100, weekday_mask="1111100"), R(2, "Day", 130, weekday_mask="0000011")]},
		{"rate": 130},
	),
	(
		"weekday rate on monday",
		req("2026-03-02", "2026-03-03"),
		{"rates": [R(1, "Day", 100, weekday_mask="1111100"), R(2, "Day", 130, weekday_mask="0000011")]},
		{"rate": 100},
	),
	(
		"weekday uses local date",
		req("2026-03-06 23:30", "2026-03-07 23:30", timezone="Asia/Tokyo"),
		{"rates": [R(1, "Day", 100, weekday_mask="1111100"), R(2, "Day", 130, weekday_mask="0000011")]},
		{"rate": 130},
	),
	(
		"valid dates",
		req("2026-05-02", "2026-05-03"),
		{"rates": [DAY, R(2, "Day", 70, valid_from="2026-05-01", valid_to="2026-05-31")]},
		{"rate": 70},
	),
	# Specific rates
	(
		"unit-specific rate",
		req("2026-03-02", "2026-03-03", rental_unit="RU-1"),
		{"rates": [DAY, R(2, "Day", 120, rental_unit="RU-1")]},
		{"rate": 120},
	),
	(
		"other unit ignores unit rate",
		req("2026-03-02", "2026-03-03", rental_unit="RU-2"),
		{"rates": [DAY, R(2, "Day", 120, rental_unit="RU-1")]},
		{"rate": 100},
	),
	(
		"customer group rate",
		req("2026-03-02", "2026-03-03", customer_group="VIP"),
		{"rates": [DAY, R(2, "Day", 80, customer_group="VIP")]},
		{"rate": 80},
	),
	# Discounts, charges, taxes
	(
		"group discount",
		req("2026-03-02", "2026-03-04", group_discount_pct=10),
		{},
		{"discount_amount": 20, "net_total": 180},
	),
	(
		"group then coupon compound",
		req("2026-03-02", "2026-03-04", group_discount_pct=10, coupon_discount_pct=50),
		{},
		{"discount_amount": 110, "net_total": 90},
	),
	(
		"fixed booking charge",
		req("2026-03-02", "2026-03-04"),
		{
			"charges": [
				{"charge_name": "Cleaning", "charge_type": "Fixed", "amount": 25, "applies_per": "Booking"}
			]
		},
		{"net_total": 225},
	),
	(
		"per unit-time charge",
		req("2026-03-02", "2026-03-04", qty=2),
		{
			"charges": [
				{"charge_name": "Insurance", "charge_type": "Fixed", "amount": 5, "applies_per": "Unit-Time"}
			]
		},
		{"net_total": 420},
	),
	(
		"percent charge on discounted base",
		req("2026-03-02", "2026-03-04", group_discount_pct=50),
		{"charges": [{"charge_name": "Service", "charge_type": "Percent", "percent": 10}]},
		{"net_total": 110},
	),
	(
		"optional charge skipped",
		req("2026-03-02", "2026-03-04"),
		{"charges": [{"charge_name": "GPS", "charge_type": "Fixed", "amount": 9, "is_mandatory": 0}]},
		{"net_total": 200, "charges": []},
	),
	(
		"tax on net",
		req("2026-03-02", "2026-03-04", tax_rate=14),
		{"charges": [{"charge_name": "Cleaning", "charge_type": "Fixed", "amount": 50}]},
		{"tax_amount": 35, "grand_total": 285},
	),
	(
		"currency precision",
		req("2026-03-02 10:00", "2026-03-02 10:07"),
		{"rates": [R(1, "Minute", 0.333)]},
		{"base_amount": 2.33},
	),
	(
		"zero precision",
		req("2026-03-02 10:00", "2026-03-02 10:07", precision=0),
		{"rates": [R(1, "Minute", 0.333)]},
		{"base_amount": 2},
	),
	(
		"aware input converted",
		req("2026-03-02T10:00:00+02:00", "2026-03-03T10:00:00+02:00", timezone="Africa/Cairo"),
		{},
		{"units": 1},
	),
]

ERROR_CASES = [
	("end before start", req("2026-03-03", "2026-03-02"), {}),
	(
		"no matching rate",
		req("2026-03-02", "2026-03-03", rental_unit="RU-9"),
		{"rates": [R(1, "Day", 100, rental_unit="RU-1")]},
	),
	("tier gap", req("2026-03-02", "2026-03-05"), {"rates": [R(1, "Day", 90, min_units=7)]}),
	("bad qty", req("2026-03-02", "2026-03-03", qty=-1), {}),
	("bad discount", req("2026-03-02", "2026-03-03", coupon_discount_pct=150), {}),
]


class TestPricing(FrappeTestCase):
	def test_cases(self):
		self.assertGreaterEqual(len(CASES) + len(ERROR_CASES), 40)
		for name, request, card_overrides, expected in CASES:
			with self.subTest(name):
				result = quote(request, {**BASE_CARD, **card_overrides})
				for key, value in expected.items():
					self.assertEqual(result[key], value, f"{name}: {key}")

	def test_errors(self):
		for name, request, card_overrides in ERROR_CASES:
			with self.subTest(name), self.assertRaises(PricingError):
				quote(request, {**BASE_CARD, **card_overrides})

	def test_applied_rule_recorded(self):
		result = quote(req("2026-03-02", "2026-03-03"), BASE_CARD)
		self.assertIn("row 1", result["applied_rule"])

	def test_hooks_adjust_result(self):
		def add_fee(request, result):
			result["grand_total"] += 1
			return result

		self.assertEqual(
			quote(req("2026-03-02", "2026-03-03"), BASE_CARD, hooks=[add_fee])["grand_total"], 101
		)
		with patch("frappe.get_hooks", return_value=[]):
			self.assertEqual(quote_with_hooks(req("2026-03-02", "2026-03-03"), BASE_CARD)["grand_total"], 100)

	def test_no_database_writes(self):
		with patch("frappe.db.sql", side_effect=AssertionError("pricing touched the database")):
			quote(req("2026-03-02", "2026-03-09"), {**BASE_CARD, "rates": [DAY, WEEK]})

	def test_unknown_unit(self):
		from datetime import UTC, datetime

		with self.assertRaises(PricingError):
			billable_units(
				"Fortnight",
				datetime(2026, 1, 1, tzinfo=UTC),
				datetime(2026, 1, 2, tzinfo=UTC),
				{},
				"Pro-rata",
			)

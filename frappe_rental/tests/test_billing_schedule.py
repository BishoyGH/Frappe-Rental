"""Billing plan and schedule (T22). Generator tests are pure; the last class uses the database."""

import random
from datetime import date, timedelta

import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_rental.services import billing
from frappe_rental.services.billing_schedule import BillingPlanError, generate, periods, regenerate

D = date
QUARTERLY = {"frequency": "Quarterly", "alignment": "Calendar period start", "timing": "In advance"}


class TestGenerator(FrappeTestCase):
	def test_quarterly_device_example(self):
		rows = generate(QUARTERLY, D(2026, 1, 1), D(2026, 12, 31), 14400)
		self.assertEqual([r["amount"] for r in rows], [3600] * 4)
		self.assertEqual([r["invoice_date"] for r in rows], [D(2026, m, 1) for m in (1, 4, 7, 10)])

	def test_quarterly_mid_month_start_prorates_first_period(self):
		rows = generate({**QUARTERLY, "period_amount": 3600}, D(2026, 1, 15), D(2026, 12, 31))
		self.assertEqual(len(rows), 4)
		self.assertEqual(rows[0]["period_to"], D(2026, 3, 31))
		self.assertEqual(rows[0]["amount"], round(3600 * 76 / 90, 2))
		self.assertEqual([r["amount"] for r in rows[1:]], [3600] * 3)

	def test_full_first_period(self):
		rows = generate(
			{**QUARTERLY, "period_amount": 3600, "proration": "Full first period"},
			D(2026, 1, 15),
			D(2026, 5, 15),
		)
		self.assertEqual(rows[0]["amount"], 3600)
		self.assertEqual(rows[1]["amount"], round(3600 * 45 / 91, 2))

	def test_no_proration_charges_partial_in_full(self):
		rows = generate(
			{**QUARTERLY, "period_amount": 100, "proration": "None"}, D(2026, 2, 1), D(2026, 4, 2)
		)
		self.assertEqual([r["amount"] for r in rows], [100, 100])

	def test_monthly_anniversary_month_end(self):
		rows = generate({"frequency": "Monthly", "period_amount": 50}, D(2026, 1, 31), D(2026, 4, 29))
		self.assertEqual([r["period_from"] for r in rows], [D(2026, 1, 31), D(2026, 2, 28), D(2026, 3, 31)])
		self.assertTrue(all(r["amount"] <= 50 for r in rows))

	def test_specific_day_in_arrears(self):
		plan = {
			"frequency": "Monthly",
			"alignment": "Specific day of month",
			"alignment_day": 5,
			"timing": "In arrears",
		}
		rows = generate(plan, D(2026, 1, 31), D(2026, 4, 4), 300)
		self.assertEqual([r["invoice_date"] for r in rows], [D(2026, 2, 4), D(2026, 3, 4), D(2026, 4, 4)])
		self.assertAlmostEqual(sum(r["amount"] for r in rows), 300, places=2)

	def test_weekly_calendar_starts_monday(self):
		rows = generate(
			{"frequency": "Weekly", "alignment": "Calendar period start"}, D(2026, 3, 4), D(2026, 3, 22), 190
		)
		self.assertEqual(rows[1]["period_from"].weekday(), 0)

	def test_custom_interval_days(self):
		plan = {"frequency": "Custom interval", "interval": 10, "interval_unit": "Days"}
		self.assertEqual(len(generate(plan, D(2026, 1, 1), D(2026, 1, 30), 300)), 3)

	def test_one_off_timings(self):
		for timing, expected in (
			("At check-in", D(2026, 1, 1)),
			("At check-out", D(2026, 1, 9)),
			("At confirmation", D(2025, 12, 20)),
		):
			rows = generate(
				{"frequency": "One-off", "timing": timing}, D(2026, 1, 1), D(2026, 1, 9), 99, D(2025, 12, 20)
			)
			self.assertEqual(rows[0]["invoice_date"], expected, timing)

	def test_milestones_split_and_rounding(self):
		rows = generate(
			{"frequency": "Milestones", "milestone_percents": "33, 33, 34"},
			D(2026, 1, 1),
			D(2026, 1, 11),
			100.01,
		)
		self.assertEqual(round(sum(r["amount"] for r in rows), 2), 100.01)
		self.assertEqual(rows[-1]["invoice_date"], D(2026, 1, 11))
		with self.assertRaises(BillingPlanError):
			generate(
				{"frequency": "Milestones", "milestone_percents": "50, 40"}, D(2026, 1, 1), D(2026, 1, 2), 1
			)

	def test_custom_first_invoice_date(self):
		plan = {**QUARTERLY, "first_invoice": "Custom date", "first_invoice_date": D(2025, 12, 15)}
		self.assertEqual(
			generate(plan, D(2026, 1, 1), D(2026, 6, 30), 10)[0]["invoice_date"], D(2025, 12, 15)
		)

	def test_invalid_plans(self):
		for plan in (
			{"frequency": "Fortnightly"},
			{"frequency": "Custom interval", "interval": 0},
			{"frequency": "Weekly", "alignment": "Specific day of month"},
			{"frequency": "Monthly", "alignment": "Specific day of month", "alignment_day": 31},
			{"frequency": "Monthly", "amount_basis": "Fixed amount per period"},
		):
			with self.assertRaises(BillingPlanError, msg=plan):
				generate(plan, D(2026, 1, 1), D(2026, 3, 1), 10)

	def test_property_periods_cover_range_and_totals_match(self):
		rnd = random.Random(22)
		freqs = ["Weekly", "Monthly", "Quarterly", "Semi-annual", "Yearly"]
		aligns = ["Rental anniversary", "Calendar period start"]
		for _ in range(300):
			start = D(2024, 1, 1) + timedelta(days=rnd.randrange(900))
			end = start + timedelta(days=rnd.randrange(800))
			plan = {"frequency": rnd.choice(freqs), "alignment": rnd.choice(aligns)}
			parts = periods(plan, start, end)
			self.assertEqual(parts[0][0], start)
			self.assertEqual(parts[-1][1], end)
			for (_, a_to, _), (b_from, _, _) in zip(parts, parts[1:], strict=False):
				self.assertEqual(a_to + timedelta(days=1), b_from)
			self.assertTrue(all(0 < w <= 1 for _, _, w in parts))
			total = round(rnd.uniform(1, 50000), 2)
			self.assertEqual(round(sum(r["amount"] for r in generate(plan, start, end, total)), 2), total)

	def test_regenerate_keeps_invoiced_rows(self):
		rows = generate(QUARTERLY, D(2026, 1, 1), D(2026, 12, 31), 14400)
		rows[0]["status"] = "Invoiced"
		# Shortened to 30 Jun: one quarter left to bill.
		new = regenerate(rows, QUARTERLY, D(2026, 1, 1), D(2026, 6, 30), 7200)
		self.assertEqual([(r["period_from"], r["amount"]) for r in new], [(D(2026, 4, 1), 3600)])
		# Shortened below what is billed: a credit row.
		credit = regenerate(rows, QUARTERLY, D(2026, 1, 1), D(2026, 2, 28), 2400)
		self.assertEqual(credit[0]["amount"], -1200)


class TestBookingSchedule(FrappeTestCase):
	def test_booking_plan_precedence_and_rebuild(self):
		doc = frappe._dict(
			rental_type=None,
			billing_plan=[frappe._dict(frequency="Monthly", alignment="Calendar period start")],
			from_datetime="2026-01-01 00:00:00",
			to_datetime="2026-04-01 00:00:00",
			net_total=300,
		)
		rows = billing.preview(doc)
		self.assertEqual([r["amount"] for r in rows], [100, 100, 100])
		doc.billing_plan = []
		self.assertEqual(billing.resolve_plan(doc), billing.DEFAULT_PLAN)

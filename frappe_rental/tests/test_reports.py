"""Reports and dashboard (T30): revenue reconciles to the GL; occupancy, overdue, history, ROI."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, nowdate

from frappe_rental.api import dashboard
from frappe_rental.services import erpnext_sync, reports
from frappe_rental.tests import test_erpnext_sync as t16
from frappe_rental.tests import test_handover as t27

REPORTS = (
	"Rental Revenue",
	"Rental Occupancy",
	"Rental Overdue Returns",
	"Rental Unit History",
	"Rental Asset ROI",
	"Rental Availability",
)


class TestReports(FrappeTestCase):
	_tax_template = t16.TestErpnextSync.__dict__["_tax_template"]
	make_fixtures = t16.TestErpnextSync.__dict__["make_fixtures"]
	booking = t16.TestErpnextSync.booking
	book = t27.TestHandover.book
	handover = t27.TestHandover.handover

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()

	def test_revenue_reconciles_to_gl(self):
		for taxes in (True, False):
			doc = self.booking(taxes=taxes)
			erpnext_sync.make_sales_invoice(doc)
		today = nowdate()
		rows = reports.revenue(today, today, self.company)
		total = flt(sum(flt(r.revenue) for r in rows), 2)
		self.assertGreater(total, 0)
		self.assertEqual(total, flt(reports.revenue_gl_total(today, today, self.company), 2))
		by_location = reports.revenue(today, today, self.company, group_by="location")
		self.assertEqual(flt(sum(flt(r.revenue) for r in by_location), 2), total)

	def test_occupancy(self):
		booking, unit = self.book("None", start="2026-08-01 00:00", end="2026-08-11 00:00")
		rows = {
			r["name"]: r
			for r in reports.occupancy(
				"2026-08-01 00:00", "2026-08-21 00:00", rental_type=booking.rental_type
			)
		}
		self.assertEqual(rows[unit.name]["booked_hours"], 240)
		self.assertEqual(rows[unit.name]["occupancy_pct"], 50)

	def test_overdue_and_history(self):
		booking, unit = self.book("None", start="2026-08-01 00:00", end="2026-08-02 00:00")
		self.handover(booking, "Check-out", "2026-08-01 00:10", unit=unit.name)
		self.assertIn(booking.name, [r.name for r in reports.overdue_returns("2026-08-03 00:00")])
		kinds = [e["kind"] for e in reports.unit_history(unit.name)]
		self.assertIn("Booking", kinds)
		self.assertIn("Check-out", kinds)

	def test_reports_execute(self):
		today = nowdate()
		filters = {
			"Rental Revenue": {"from_date": today, "to_date": today, "group_by": "rental_type"},
			"Rental Occupancy": {"from_date": today, "to_date": add_days(today, 7)},
			"Rental Overdue Returns": {},
			"Rental Unit History": {"rental_unit": frappe.db.get_value("Rental Unit", {})},
			"Rental Asset ROI": {},
			"Rental Availability": {
				"from_datetime": f"{add_days(today, 30)} 10:00",
				"to_datetime": f"{add_days(today, 31)} 10:00",
			},
		}
		from frappe.desk.query_report import run

		for name in REPORTS:
			with self.subTest(report=name):
				self.assertTrue(frappe.db.exists("Report", name))
				result = run(name, filters=filters[name])
				self.assertIn("result", result)

	def test_dashboard_kpis(self):
		data = dashboard.kpis()
		for key in ("units", "active_bookings", "overdue_returns", "revenue_this_month", "deposits_held"):
			self.assertIn(key, data)

	def test_today_board_shape_and_permission(self):
		data = dashboard.today()
		for key in ("arrivals", "departures", "in_house", "overdue"):
			self.assertIsInstance(data[key], list)
		self.assertEqual(reports.today_board(now="2026-01-01 10:00", location="__none__")["arrivals"], [])
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				dashboard.today()
		finally:
			frappe.set_user("Administrator")

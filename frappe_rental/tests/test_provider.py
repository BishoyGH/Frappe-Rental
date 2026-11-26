"""Provider scheduling (T45): working hours, holidays, slots, own schedule, Project and Timesheet billing."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, random_string

from frappe_rental.services import availability, provider
from frappe_rental.tests import test_erpnext_sync as t16

MONDAY = "2026-03-02"  # a Monday
TUESDAY = "2026-03-03"


def make_schedule(holidays=()):
	holiday_list = None
	if holidays:
		holiday_list = (
			frappe.get_doc(
				{
					"doctype": "Holiday List",
					"holiday_list_name": f"T45 {random_string(6)}",
					"from_date": "2026-01-01",
					"to_date": "2026-12-31",
					"holidays": [{"holiday_date": d, "description": "Off"} for d in holidays],
				}
			)
			.insert()
			.name
		)
	return frappe.get_doc(
		{
			"doctype": "Rental Schedule",
			"schedule_name": f"T45 {random_string(6)}",
			"holiday_list": holiday_list,
			"slot_minutes": 60,
			"slots": [
				{"weekday": "Monday", "from_time": "09:00:00", "to_time": "12:00:00"},
				{"weekday": "Monday", "from_time": "13:00:00", "to_time": "17:00:00"},
			],
		}
	).insert()


def make_hourly_fixtures(company):
	currency = frappe.db.get_value("Company", company, "default_currency")
	if not frappe.db.exists("Rental Rate Card", "T45 Hourly"):
		frappe.get_doc(
			{
				"doctype": "Rental Rate Card",
				"card_name": "T45 Hourly",
				"currency": currency,
				"rates": [{"time_unit": "Hour", "rate": 50}],
			}
		).insert()
	if not frappe.db.exists("Rental Type", "T45 Shoot"):
		frappe.get_doc(
			{
				"doctype": "Rental Type",
				"type_name": "T45 Shoot",
				"mode": "Resource",
				"time_unit": "Hour",
				"requires_hold": 0,
			}
		).insert()
	if not frappe.db.exists("Gender", "Female"):
		frappe.get_doc({"doctype": "Gender", "gender": "Female"}).insert()


class TestProvider(FrappeTestCase):
	_tax_template = t16.TestErpnextSync.__dict__["_tax_template"]
	make_fixtures = t16.TestErpnextSync.__dict__["make_fixtures"]

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()
		make_hourly_fixtures(cls.company)

	def _unit(self, **kw):
		item = frappe.get_doc(
			{
				"doctype": "Rental Item",
				"item_name": f"T45 {random_string(6)}",
				"rental_type": "T45 Shoot",
				"rate_card": "T45 Hourly",
			}
		).insert()
		return (
			frappe.get_doc(
				{
					"doctype": "Rental Unit",
					"unit_name": f"T45 {random_string(6)}",
					"rental_item": item.name,
					**kw,
				}
			)
			.insert()
			.name
		)

	def booking(self, unit, start=f"{MONDAY} 09:00", end=f"{MONDAY} 10:00"):
		return frappe.get_doc(
			{
				"doctype": "Rental Booking",
				"customer": self.customer,
				"rental_type": "T45 Shoot",
				"company": self.company,
				"from_datetime": start,
				"to_datetime": end,
				"lines": [
					{
						"rental_item": frappe.db.get_value("Rental Unit", unit, "rental_item"),
						"rental_unit": unit,
						"qty": 1,
					}
				],
			}
		).insert()

	def provider_unit(self, holidays=(), employee=None):
		schedule = make_schedule(holidays)
		return self._unit(unit_type="Provider", working_hours=schedule.name, employee=employee)

	def test_schedule_validation(self):
		doc = frappe.get_doc(
			{
				"doctype": "Rental Schedule",
				"schedule_name": f"T45 {random_string(6)}",
				"slots": [{"weekday": "Monday", "from_time": "12:00:00", "to_time": "09:00:00"}],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc.insert()

	def test_slots_skip_breaks_bookings_and_holidays(self):
		unit = self.provider_unit(holidays=["2026-03-09"])
		slots = provider.slots(unit, MONDAY, minutes=60)
		self.assertEqual(
			[str(s["from_datetime"])[11:16] for s in slots],
			["09:00", "10:00", "11:00", "13:00", "14:00", "15:00", "16:00"],
		)
		self.assertEqual(provider.slots(unit, TUESDAY), [])
		self.assertEqual(provider.slots(unit, "2026-03-09"), [])
		self.booking(unit, f"{MONDAY} 10:00", f"{MONDAY} 11:00").submit()
		starts = [str(s["from_datetime"])[11:16] for s in provider.slots(unit, MONDAY, minutes=120)]
		self.assertEqual(starts, ["13:00", "14:00", "15:00"])

	def test_booking_outside_hours_is_refused(self):
		unit = self.provider_unit(holidays=["2026-03-09"])
		with self.assertRaises(availability.UnavailableError):
			self.booking(unit, f"{MONDAY} 11:30", f"{MONDAY} 13:30")
		with self.assertRaises(availability.UnavailableError):
			self.booking(unit, f"{TUESDAY} 10:00", f"{TUESDAY} 11:00")
		with self.assertRaises(availability.UnavailableError):
			self.booking(unit, "2026-03-09 10:00", "2026-03-09 11:00")
		self.assertTrue(self.booking(unit, f"{MONDAY} 13:00", f"{MONDAY} 17:00").name)

	def test_units_without_schedule_are_unrestricted(self):
		unit = self._unit()
		self.assertTrue(provider.within_hours(unit, f"{TUESDAY} 02:00", f"{TUESDAY} 03:00"))

	def test_photographer_booking_project_and_timesheet_billing(self):
		unit = self.provider_unit()
		b = self.booking(unit, f"{MONDAY} 09:00", f"{MONDAY} 12:00")
		b.submit()
		project = frappe.db.get_value("Project", {"rental_booking": b.name})
		self.assertTrue(project)
		self.assertEqual(provider.ensure_project(b), project)  # idempotent

		ts = frappe.get_doc(
			{
				"doctype": "Timesheet",
				"company": self.company,
				"customer": self.customer,
				"time_logs": [
					{
						"project": project,
						"from_time": f"{MONDAY} 09:00:00",
						"hours": 3,
						"is_billable": 1,
						"billing_hours": 3,
						"billing_rate": 50,
					}
				],
			}
		).insert()
		ts.submit()
		events = frappe.get_all(
			"Rental Billable Event",
			filters={"rental_booking": b.name, "event_type": "Timesheet"},
			fields=["name", "amount"],
		)
		self.assertEqual(len(events), 1)
		self.assertEqual(flt(events[0].amount), 150)
		self.assertEqual(provider.bill_timesheet(ts), [events[0].name])  # once per Timesheet

	def test_non_provider_booking_gets_no_project(self):
		b = self.booking(self._unit())
		b.submit()
		self.assertFalse(frappe.db.exists("Project", {"rental_booking": b.name}))

	def test_my_schedule_lists_own_bookings_only(self):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"t45-{random_string(6)}@example.com",
				"first_name": "Pat",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
		employee = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "Pat",
				"gender": "Female",
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"company": self.company,
				"user_id": user.name,
			}
		).insert()
		mine = self.provider_unit(employee=employee.name)
		other = self.provider_unit()
		b1 = self.booking(mine, f"{MONDAY} 09:00", f"{MONDAY} 10:00")
		self.booking(other, f"{MONDAY} 09:00", f"{MONDAY} 10:00")
		rows = provider.my_schedule(user.name, MONDAY, MONDAY)
		self.assertEqual([r["name"] for r in rows], [b1.name])
		self.assertEqual(rows[0]["rental_unit"], mine)
		self.assertEqual(provider.my_schedule("Guest", MONDAY, MONDAY), [])

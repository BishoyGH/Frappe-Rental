import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.api import availability as av_api
from frappe_rental.api import booking as api
from frappe_rental.compat.erpnext import ensure_setup_complete
from frappe_rental.services.availability import UnavailableError
from frappe_rental.services.setup import create_defaults
from frappe_rental.tests.test_lifecycle import make_type
from frappe_rental.tests.test_staff_app import make_user
from frappe_rental.tests.utils import make_customer


class TestTimeline(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		company = ensure_setup_complete()
		create_defaults()
		currency = frappe.db.get_value("Company", company, "default_currency")
		if not frappe.db.exists("Rental Rate Card", "T19 Card"):
			frappe.get_doc(
				{
					"doctype": "Rental Rate Card",
					"card_name": "T19 Card",
					"currency": currency,
					"rates": [{"time_unit": "Day", "rate": 50}],
				}
			).insert()
		cls.rtype = make_type(f"T19 Type {random_string(4)}", requires_hold=1)
		cls.customer = make_customer()
		cls.item = (
			frappe.get_doc(
				{
					"doctype": "Rental Item",
					"item_name": f"T19 Boat {random_string(4)}",
					"rental_type": cls.rtype,
					"rate_card": "T19 Card",
				}
			)
			.insert()
			.name
		)
		cls.u1, cls.u2 = (
			frappe.get_doc(
				{
					"doctype": "Rental Unit",
					"unit_name": f"T19 {n} {random_string(4)}",
					"rental_item": cls.item,
				}
			)
			.insert()
			.name
			for n in (1, 2)
		)

	def tearDown(self):
		frappe.set_user("Administrator")

	def book(self, unit, start, end, hold=1):
		return api.create(
			{
				"customer": self.customer,
				"rental_type": self.rtype,
				"from_datetime": start,
				"to_datetime": end,
				"lines": [{"rental_item": self.item, "rental_unit": unit}],
			},
			hold=hold,
		)["name"]

	def test_timeline_rows_and_events(self):
		b = self.book(self.u1, "2027-03-02 10:00", "2027-03-04 10:00")
		frappe.get_doc(
			{
				"doctype": "Rental Block",
				"rental_unit": self.u2,
				"reason": "Maintenance",
				"from_datetime": "2027-03-05 00:00",
				"to_datetime": "2027-03-06 00:00",
			}
		).insert()
		out = av_api.timeline("2027-03-01 00:00", "2027-03-08 00:00", rental_type=self.rtype)
		rows = {u["name"]: u for u in out["units"]}
		self.assertEqual(set(rows), {self.u1, self.u2})
		ev = rows[self.u1]["events"]
		self.assertEqual(
			[(e["kind"], e["name"], e["status"], e["movable"]) for e in ev], [("booking", b, "Hold", True)]
		)
		self.assertEqual(rows[self.u2]["events"][0]["kind"], "block")
		empty = av_api.timeline("2027-04-01 00:00", "2027-04-08 00:00", rental_type=self.rtype)
		self.assertTrue(all(not u["events"] for u in empty["units"]))

	def test_timeline_limits(self):
		with self.assertRaises(frappe.ValidationError):
			av_api.timeline("2027-01-01", "2027-06-01")
		with self.assertRaises(frappe.ValidationError):
			av_api.timeline("2027-01-02", "2027-01-01")

	def test_move_hold_to_free_slot_and_unit(self):
		b = self.book(self.u1, "2027-05-02 10:00", "2027-05-03 10:00")
		api.move(b, "2027-05-10 10:00", "2027-05-12 10:00", self.u2)
		doc = frappe.get_doc("Rental Booking", b)
		self.assertEqual(doc.lines[0].rental_unit, self.u2)
		self.assertEqual(doc.grand_total, 100)
		cache = frappe.get_all(
			"Rental Availability Cache",
			filters={"source_name": b},
			fields=["rental_unit"],
			pluck="rental_unit",
		)
		self.assertEqual(cache, [self.u2])

	def test_move_conflict_rejected(self):
		a = self.book(self.u1, "2027-06-02 10:00", "2027-06-04 10:00")
		b = self.book(self.u2, "2027-06-02 10:00", "2027-06-04 10:00")
		with self.assertRaises(UnavailableError):
			api.move(b, "2027-06-03 10:00", "2027-06-05 10:00", self.u1)
		draft = self.book(self.u2, "2027-06-10 10:00", "2027-06-11 10:00", hold=0)
		with self.assertRaises(UnavailableError):
			api.move(draft, "2027-06-02 12:00", "2027-06-03 12:00", self.u1)
		self.assertEqual(frappe.db.get_value("Rental Booking Line", {"parent": b}, "rental_unit"), self.u2)
		self.assertTrue(a)

	def test_move_confirmed_rejected(self):
		b = self.book(self.u1, "2027-07-02 10:00", "2027-07-03 10:00")
		api.confirm(b)
		with self.assertRaises(frappe.ValidationError):
			api.move(b, "2027-07-05 10:00", "2027-07-06 10:00")

	def test_permissions(self):
		frappe.set_user(make_user())
		with self.assertRaises(frappe.PermissionError):
			av_api.timeline("2027-03-01", "2027-03-02")

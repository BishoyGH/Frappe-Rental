import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_rental.api import waitlist as api
from frappe_rental.services import demo, lifecycle, waitlist

START, END = "2029-03-03 10:00", "2029-03-05 10:00"


class TestWaitlist(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.data = demo.make_demo()
		cls.item = cls.data["items"]["Device"]
		cls.customer = cls.data["customers"][0]
		src = frappe.get_doc("Rental Item", cls.item)
		alt = frappe.get_doc(
			{
				"doctype": "Rental Item",
				"item_name": "Waitlist alt camera",
				"rental_type": src.rental_type,
				"location": src.location,
				"rate_card": src.rate_card,
			}
		).insert()
		cls.alt = alt.name
		cls.alt_unit = (
			frappe.get_doc(
				{
					"doctype": "Rental Unit",
					"unit_name": "WL-ALT-1",
					"rental_item": alt.name,
					"serial_no": demo._serial_no("WL-ALT-1"),
				}
			)
			.insert()
			.name
		)

	def fill(self, start=START, end=END):
		n = frappe.db.count("Rental Unit", {"rental_item": self.item})
		return [demo.book(self.customer, "Device", self.item, start, end) for _ in range(n)]

	def test_cancel_notifies_waiting_entry_once(self):
		bookings = self.fill()
		entry = waitlist.add(self.customer, self.item, START, END)
		self.assertEqual(waitlist.check([self.item]), [])
		lifecycle.cancel(frappe.get_doc("Rental Booking", bookings[0]))
		self.assertEqual(frappe.db.get_value(waitlist.DOCTYPE, entry, "status"), "Notified")
		logs = frappe.get_all("Rental Event Log", {"reference_name": entry}, pluck="event")
		self.assertEqual(logs, ["waitlist_available"])
		lifecycle.cancel(frappe.get_doc("Rental Booking", bookings[1]))
		self.assertEqual(len(frappe.get_all("Rental Event Log", {"reference_name": entry})), 1)

	def test_entry_for_other_period_stays_waiting(self):
		bookings = self.fill("2029-04-03 10:00", "2029-04-05 10:00")
		self.fill("2029-05-03 10:00", "2029-05-05 10:00")
		entry = waitlist.add(self.customer, self.item, "2029-05-03 10:00", "2029-05-04 10:00")
		lifecycle.cancel(frappe.get_doc("Rental Booking", bookings[0]))
		self.assertEqual(frappe.db.get_value(waitlist.DOCTYPE, entry, "status"), "Waiting")

	def test_substitutes_offer_other_item_of_type(self):
		self.fill("2029-06-03 10:00", "2029-06-05 10:00")
		out = waitlist.substitutes(self.item, "2029-06-03 10:00", "2029-06-05 10:00")
		self.assertEqual(out["units"], [])
		self.assertIn(self.alt, [i["rental_item"] for i in out["items"]])
		self.assertEqual(
			[i["rental_unit"] for i in out["items"] if i["rental_item"] == self.alt], [self.alt_unit]
		)
		free = waitlist.substitutes(self.item, "2029-07-03 10:00", "2029-07-05 10:00")
		self.assertTrue(free["units"])

	def test_unit_must_belong_to_item(self):
		with self.assertRaises(frappe.ValidationError):
			waitlist.add(self.customer, self.item, START, END, rental_unit=self.alt_unit)

	def test_expire_cancels_started_entries(self):
		entry = waitlist.add(self.customer, self.item, "2029-08-03 10:00", "2029-08-05 10:00")
		waitlist.expire(now="2029-08-04 00:00")
		self.assertEqual(frappe.db.get_value(waitlist.DOCTYPE, entry, "status"), "Cancelled")

	def test_api_requires_permission(self):
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				api.add(self.customer, self.item, START, END)
			with self.assertRaises(frappe.PermissionError):
				api.substitutes(self.item, START, END)
		finally:
			frappe.set_user("Administrator")

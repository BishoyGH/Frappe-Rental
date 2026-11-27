import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from frappe_rental.services import demo, erpnext_sync, events, lifecycle

CALLS = []


def record(event, log):
	CALLS.append((event, log.reference_name))


class TestEvents(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.data = demo.make_demo()

	def logs(self, name, event=None):
		f = {"reference_name": name}
		if event:
			f["event"] = event
		return frappe.get_all("Rental Event Log", filters=f, pluck="event", order_by="creation asc")

	def test_lifecycle_events_fire_once(self):
		name = demo.book(
			self.data["customers"][0],
			"Device",
			self.data["items"]["Device"],
			"2028-01-03 10:00",
			"2028-01-05 10:00",
		)
		doc = frappe.get_doc("Rental Booking", name)
		self.assertEqual(self.logs(name, "booking_confirmed"), ["booking_confirmed"])
		# A second emit for the same booking is a no-op
		self.assertIsNone(events.emit("booking_confirmed", doc))
		self.assertEqual(len(self.logs(name, "booking_confirmed")), 1)
		invoice = erpnext_sync.make_sales_invoice(doc)
		erpnext_sync.make_sales_invoice(doc)
		self.assertEqual(self.logs(invoice), ["invoice_created"])
		lifecycle.cancel(doc)
		self.assertEqual(self.logs(name, "booking_cancelled"), ["booking_cancelled"])

	def test_payload_shape(self):
		name = demo.book(
			self.data["customers"][0],
			"Device",
			self.data["items"]["Device"],
			"2028-02-03 10:00",
			"2028-02-05 10:00",
		)
		log = frappe.get_doc("Rental Event Log", {"reference_name": name, "event": "booking_confirmed"})
		p = json.loads(log.payload)
		for key in (
			"event",
			"doctype",
			"name",
			"customer",
			"status",
			"from_datetime",
			"to_datetime",
			"grand_total",
			"items",
		):
			self.assertIn(key, p)
		self.assertEqual(p["status"], "Confirmed")

	def test_hold_reminder_once(self):
		name = demo.book(
			self.data["customers"][1],
			"Device",
			self.data["items"]["Device"],
			"2028-03-03 10:00",
			"2028-03-05 10:00",
			confirm=False,
		)
		self.assertIn("booking_held", self.logs(name))
		frappe.db.set_value("Rental Booking", name, "hold_expires_on", add_to_date(now_datetime(), minutes=5))
		self.assertGreaterEqual(events.remind_expiring_holds(), 1)
		events.remind_expiring_holds()
		self.assertEqual(self.logs(name, "hold_expiring"), ["hold_expiring"])

	def test_handler_hook_and_unknown_event(self):
		CALLS.clear()
		original = frappe.get_hooks

		def hooks(name=None, *a, **kw):
			if name == "rental_event_handlers":
				return ["frappe_rental.tests.test_events.record"]
			return original(name, *a, **kw)

		frappe.get_hooks = hooks
		try:
			name = demo.book(
				self.data["customers"][0],
				"Device",
				self.data["items"]["Device"],
				"2028-04-03 10:00",
				"2028-04-05 10:00",
			)
		finally:
			frappe.get_hooks = original
		self.assertIn(("booking_confirmed", name), CALLS)
		with self.assertRaises(frappe.ValidationError):
			events.emit("nope", frappe.get_doc("Rental Booking", name))

	def test_notification_templates(self):
		events.install_notifications()
		events.install_notifications()
		n = frappe.get_doc("Notification", "Rental: booking confirmed")
		self.assertEqual(n.document_type, "Rental Event Log")
		self.assertEqual(n.enabled, 0)

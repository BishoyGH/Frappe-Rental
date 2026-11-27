import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from frappe_rental.api import booking as booking_api
from frappe_rental.api import ops
from frappe_rental.services import demo
from frappe_rental.tests.test_staff_app import make_user


class TestStaffOps(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.data = demo.make_demo()
		cls.customer = cls.data["customers"][0]
		cls.device = cls.data["items"]["Device"]

	def tearDown(self):
		frappe.set_user("Administrator")

	def device_booking(self, day):
		return demo.book(
			self.customer, "Device", self.device, f"2031-01-{day:02d} 10:00", f"2031-01-{day + 2:02d} 10:00"
		)

	def test_scan_first_handover_flow(self):
		name = self.device_booking(3)
		state = ops.handover_state(name)
		self.assertEqual(state["next_step"], "Check-out")
		unit = state["lines"][0]["rental_unit"]
		serial = state["lines"][0]["serial_no"]
		found = ops.find_booking(serial)
		self.assertEqual(found["name"], name)
		booking_api.checkout(name, scans=[serial])
		state = ops.handover_state(name)
		self.assertTrue(state["lines"][0]["out"])
		self.assertEqual(state["next_step"], "Return")
		self.assertEqual(ops.find_booking(unit)["name"], name)
		booking_api.checkin(name, lines=[{"rental_unit": unit, "condition": "Damaged", "notes": "Scratch"}])
		state = ops.handover_state(name)
		self.assertIsNone(state["next_step"])
		self.assertEqual([h["handover_type"] for h in state["history"]], ["Check-out", "Return"])
		damages = ops.panels(name)["damages"]
		self.assertEqual(len(damages), 1)
		self.assertIsNone(ops.find_booking("no-such-code"))

	def test_damage_approve_and_write_off(self):
		name = self.device_booking(9)
		booking_api.checkout(name)
		unit = ops.handover_state(name)["lines"][0]["rental_unit"]
		booking_api.checkin(name, lines=[{"rental_unit": unit, "condition": "Damaged"}])
		report = ops.panels(name)["damages"][0]["name"]
		ops.approve_damage(report, 50)
		self.assertEqual(frappe.db.get_value("Rental Damage Report", report, "approved_amount"), 50)
		out = ops.settle_damage(report, "Write-off")
		self.assertEqual(out["status"], "Written Off")
		with self.assertRaises(frappe.ValidationError):
			ops.settle_damage(report, "Teleport")

	def test_billing_schedule_edit(self):
		customer = self.customer
		contract = demo.signed_contract(customer, "2031-03-01")
		name = demo.book(
			customer,
			"Apartment",
			self.data["items"]["Apartment"],
			"2031-03-01 14:00",
			"2031-06-01 14:00",
			contract=contract,
		)
		bill = ops.billing(name)
		rows = bill["rows"]
		self.assertTrue(rows)
		self.assertAlmostEqual(sum(flt(r["amount"]) for r in rows), flt(bill["net_total"]), places=2)
		if len(rows) > 1:
			a, b = rows[0], rows[1]
			moved = [
				{"idx": a["idx"], "amount": flt(a["amount"]) - 10, "adjustment_note": "Agreed"},
				{"idx": b["idx"], "amount": flt(b["amount"]) + 10},
			]
			out = ops.save_schedule(name, moved)
			self.assertAlmostEqual(flt(out["rows"][0]["amount"]), flt(a["amount"]) - 10, places=2)
			self.assertEqual(out["rows"][0]["adjustment_note"], "Agreed")
		with self.assertRaises(frappe.ValidationError):
			ops.save_schedule(name, [{"idx": rows[0]["idx"], "amount": flt(rows[0]["amount"]) + 1}])

	def test_permissions(self):
		name = self.device_booking(15)
		frappe.set_user(make_user("Rental Accountant"))
		with self.assertRaises(frappe.PermissionError):
			ops.save_schedule(name, [])
		frappe.set_user("Guest")
		for fn in (ops.handover_state, ops.billing, ops.panels):
			with self.assertRaises(frappe.PermissionError):
				fn(name)
		with self.assertRaises(frappe.PermissionError):
			ops.find_booking(name)

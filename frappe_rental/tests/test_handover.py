"""Handover and return (T27): status rules, late fees, and stock or asset moves per identification mode."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, random_string

from frappe_rental.compat import erpnext as compat
from frappe_rental.services import handover
from frappe_rental.tests import test_erpnext_sync as t16


def rental_type(mode):
	name = f"T27 {mode}"
	if not frappe.db.exists("Rental Type", name):
		frappe.get_doc(
			{
				"doctype": "Rental Type",
				"type_name": name,
				"mode": "Resource",
				"time_unit": "Day",
				"requires_hold": 0,
				"identification_mode": mode,
			}
		).insert()
	return name


class TestHandover(FrappeTestCase):
	_tax_template = t16.TestErpnextSync.__dict__["_tax_template"]
	make_fixtures = t16.TestErpnextSync.__dict__["make_fixtures"]

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()
		cls.warehouse = frappe.db.get_value(
			"Warehouse", {"company": cls.company, "is_group": 0, "name": ["not like", "%Rented Out%"]}
		)
		frappe.db.set_single_value("Rental Settings", {"grace_period_minutes": 30, "late_fee_rate": 10})

	def book(self, mode, unit_kw=None, item_kw=None, start="2026-07-01 10:00", end="2026-07-03 10:00"):
		item = frappe.get_doc(
			{
				"doctype": "Rental Item",
				"item_name": f"T27 {random_string(6)}",
				"rental_type": rental_type(mode),
				"rate_card": "T16 Card",
				**(item_kw or {}),
			}
		).insert()
		unit = frappe.get_doc(
			{
				"doctype": "Rental Unit",
				"unit_name": f"T27 {random_string(6)}",
				"rental_item": item.name,
				**(unit_kw or {}),
			}
		).insert()
		doc = frappe.get_doc(
			{
				"doctype": "Rental Booking",
				"customer": self.customer,
				"rental_type": rental_type(mode),
				"company": self.company,
				"from_datetime": start,
				"to_datetime": end,
				"lines": [{"rental_item": item.name, "rental_unit": unit.name, "qty": 1}],
			}
		).insert()
		doc.submit()
		doc.reload()
		return doc, unit

	def handover(self, booking, kind, when, scan=None, unit=None, condition="Good"):
		doc = frappe.get_doc(
			{
				"doctype": "Rental Handover",
				"rental_booking": booking.name,
				"handover_type": kind,
				"posted_on": when,
				"scan_input": scan,
				"lines": [] if scan else [{"rental_unit": unit, "condition": condition}],
				"checklist": [{"check": "Clean", "done": 1}],
				"signed_by": "Customer",
			}
		)
		doc.insert()
		doc.submit()
		return doc

	def test_none_mode_status_and_events(self):
		booking, unit = self.book("None")
		out = self.handover(booking, "Check-out", "2026-07-01 10:05", scan=unit.name)
		self.assertEqual(len(out.lines), 1)
		self.assertEqual(frappe.db.get_value("Rental Unit", unit.name, "status"), "Occupied")
		self.assertEqual(frappe.db.get_value("Rental Booking", booking.name, "status"), "Checked Out")
		self.assertTrue(
			frappe.db.exists("Rental Event Log", {"event": "handover_done", "reference_name": out.name})
		)
		back = self.handover(booking, "Return", "2026-07-03 10:10", unit=unit.name)
		self.assertFalse(back.is_late)  # inside the 30 minute grace
		self.assertEqual(frappe.db.get_value("Rental Unit", unit.name, "status"), "Available")
		self.assertEqual(frappe.db.get_value("Rental Booking", booking.name, "status"), "Returned")

	def test_return_needs_checkout_and_booked_unit(self):
		booking, unit = self.book("None")
		with self.assertRaises(frappe.ValidationError):
			self.handover(booking, "Return", "2026-07-03 10:00", unit=unit.name)
		other, other_unit = self.book("None")
		with self.assertRaises(frappe.ValidationError):
			self.handover(booking, "Check-out", "2026-07-01 10:00", unit=other_unit.name)

	def test_late_return_queues_fee_once(self):
		booking, unit = self.book("None")
		self.handover(booking, "Check-out", "2026-07-01 10:00", unit=unit.name)
		handover.check_overdue("2026-07-04 08:00")
		handover.check_overdue("2026-07-04 09:00")  # once a day
		self.assertEqual(
			frappe.db.count("Rental Event Log", {"event": "overdue", "reference_name": booking.name}), 1
		)
		back = self.handover(booking, "Return", "2026-07-04 11:00", unit=unit.name, condition="Damaged")
		self.assertTrue(back.is_late)
		self.assertEqual(back.late_minutes, 24 * 60 + 30)
		fees = frappe.get_all(
			"Rental Billable Event", filters={"source_name": back.name}, fields=["event_type", "amount"]
		)
		self.assertEqual(len(fees), 1)
		self.assertEqual(flt(fees[0].amount, 2), flt(flt(booking.net_total) * 0.10 * 2, 2))  # 2 started days
		self.assertEqual(frappe.db.get_value("Rental Unit", unit.name, "status"), "Maintenance")

	def test_cancel_checkout_restores(self):
		booking, unit = self.book("None")
		out = self.handover(booking, "Check-out", "2026-07-01 10:00", unit=unit.name)
		out.cancel()
		self.assertEqual(frappe.db.get_value("Rental Unit", unit.name, "status"), "Available")
		self.assertEqual(frappe.db.get_value("Rental Booking", booking.name, "status"), "Confirmed")

	def test_serial_mode_moves_stock_and_records_customer(self):
		compat.enable_serial_numbers()
		code = f"T27-SER-{random_string(5)}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}),
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"has_serial_no": 1,
			}
		).insert()
		sn = f"{code}-1"
		se = frappe.new_doc("Stock Entry")
		se.update(
			{"stock_entry_type": "Material Receipt", "purpose": "Material Receipt", "company": self.company}
		)
		row = {"item_code": code, "qty": 1, "t_warehouse": self.warehouse, "basic_rate": 100, "serial_no": sn}
		if frappe.get_meta("Stock Entry Detail").has_field("use_serial_batch_fields"):
			row["use_serial_batch_fields"] = 1
		se.append("items", row)
		se.insert()
		se.submit()
		booking, unit = self.book(
			"Serial", unit_kw={"serial_no": sn, "warehouse": self.warehouse}, item_kw={"item_code": code}
		)
		out = self.handover(booking, "Check-out", "2026-07-01 10:00", scan=sn)
		self.assertTrue(out.stock_entry)
		rented_out = frappe.db.get_single_value("Rental Settings", "rented_out_warehouse")
		self.assertEqual(frappe.db.get_value("Serial No", sn, "warehouse"), rented_out)
		self.assertEqual(frappe.db.get_value("Serial No", sn, "rental_customer"), self.customer)
		self.handover(booking, "Return", "2026-07-03 10:00", unit=unit.name)
		self.assertEqual(frappe.db.get_value("Serial No", sn, "warehouse"), self.warehouse)
		self.assertIsNone(frappe.db.get_value("Serial No", sn, "rental_customer"))
		history = handover.serial_history(sn)
		self.assertEqual(
			[(h.handover_type, h.customer) for h in history],
			[("Check-out", self.customer), ("Return", self.customer)],
		)

	def test_asset_mode_moves_location(self):
		home = f"T27 Home {random_string(4)}"
		frappe.get_doc({"doctype": "Location", "location_name": home}).insert()
		asset = f"T27-AST-{random_string(5)}"
		frappe.get_doc(
			{
				"doctype": "Asset",
				"name": asset,
				"asset_name": asset,
				"company": self.company,
				"location": home,
				"docstatus": 1,
				"status": "Submitted",
				"item_code": t16_item(),
			}
		).db_insert()
		booking, unit = self.book("Asset", unit_kw={"asset": asset})
		out = self.handover(booking, "Check-out", "2026-07-01 10:00", unit=unit.name)
		self.assertTrue(out.asset_movements)
		self.assertEqual(frappe.db.get_value("Asset", asset, "location"), handover.RENTED_OUT_LOCATION)
		self.handover(booking, "Return", "2026-07-03 10:00", unit=unit.name)
		self.assertEqual(frappe.db.get_value("Asset", asset, "location"), home)

	def test_pooled_units_stay_available(self):
		booking, unit = self.book(
			"Pooled", unit_kw={"identification_mode": "Pooled", "quantity_available": 5}
		)
		self.handover(booking, "Check-out", "2026-07-01 10:00", unit=unit.name)
		self.assertEqual(frappe.db.get_value("Rental Unit", unit.name, "status"), "Available")


def t16_item():
	return frappe.db.get_value("Item", {"is_stock_item": 0, "disabled": 0}, "name")

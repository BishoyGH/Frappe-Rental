"""Demo data (T21, T59): items, units and customers for the presets, built in code.

`make_demo` covers Device and Apartment (used by tests); `make_full_demo` adds every other preset.

``make_demo`` is idempotent: running it again creates nothing new. Bookings are optional, because the
acceptance scenarios create their own.
"""

import frappe
from frappe.utils import add_days, getdate, now_datetime

from frappe_rental.compat.erpnext import enable_serial_numbers, ensure_setup_complete
from frappe_rental.services import rental_type
from frappe_rental.services.setup import create_defaults

LOCATION = "Demo Cairo"
CARDS = {"Demo Device Daily": ("Day", 630), "Demo Apartment Monthly": ("Month", 16000)}
ITEMS = {
	"Demo Sony A7 IV kit": ("Device", "Demo Device Daily", ["CAM-014", "CAM-009", "CAM-021"]),
	"Demo 2BR apartment, Maadi": ("Apartment", "Demo Apartment Monthly", ["Apt 4B", "Apt 5A"]),
}
CUSTOMERS = ("Demo Nile Studios", "Demo Sara Mahmoud")


def make_demo(with_bookings: bool = False) -> dict:
	company = ensure_setup_complete()
	create_defaults()
	rental_type.install_presets()
	currency = frappe.db.get_value("Company", company, "default_currency")
	if not frappe.db.exists("Rental Location", LOCATION):
		frappe.get_doc({"doctype": "Rental Location", "location_name": LOCATION, "company": company}).insert()
	for card, (unit, rate) in CARDS.items():
		if not frappe.db.exists("Rental Rate Card", card):
			frappe.get_doc(
				{
					"doctype": "Rental Rate Card",
					"card_name": card,
					"currency": currency,
					"rates": [{"time_unit": unit, "rate": rate}],
				}
			).insert()
	items = {}
	for name, (rtype, card, units) in ITEMS.items():
		item = frappe.db.get_value("Rental Item", {"item_name": name})
		if not item:
			item = (
				frappe.get_doc(
					{
						"doctype": "Rental Item",
						"item_name": name,
						"rental_type": rtype,
						"rate_card": card,
						"location": LOCATION,
						"is_published": 1,
					}
				)
				.insert()
				.name
			)
		serial = frappe.db.get_value("Rental Type", rtype, "identification_mode") == "Serial"
		for unit in units:
			if not frappe.db.exists("Rental Unit", {"unit_name": unit, "rental_item": item}):
				frappe.get_doc(
					{
						"doctype": "Rental Unit",
						"unit_name": unit,
						"rental_item": item,
						"location": LOCATION,
						"serial_no": _serial_no(f"DEMO-{unit}") if serial else None,
					}
				).insert()
		items[rtype] = item
	from frappe_rental.tests.utils import make_customer

	customers = [make_customer(c) for c in CUSTOMERS]
	out = {"items": items, "customers": customers, "location": LOCATION, "bookings": []}
	if with_bookings and not frappe.db.exists("Rental Booking", {"customer": customers[0]}):
		start = getdate(add_days(now_datetime(), 3))
		out["bookings"].append(
			book(
				customers[0],
				"Device",
				items["Device"],
				f"{start} 10:00",
				f"{add_days(start, 3)} 10:00",
				confirm=False,
			)
		)
	return out


SERIAL_ITEM = "DEMO-CAMERA-BODY"


def _serial_no(serial: str) -> str:
	"""A Serial No of a serialised stock item, for presets that identify units by serial (Device)."""
	if not frappe.db.exists("Item", SERIAL_ITEM):
		from frappe_rental.services.rental_item import _item_group, _stock_uom

		enable_serial_numbers()
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": SERIAL_ITEM,
				"item_name": "Demo camera body",
				"item_group": _item_group(),
				"stock_uom": _stock_uom(),
				"is_stock_item": 1,
				"has_serial_no": 1,
			}
		).insert()
	if not frappe.db.exists("Serial No", serial):
		frappe.get_doc({"doctype": "Serial No", "serial_no": serial, "item_code": SERIAL_ITEM}).insert()
	return serial


def book(
	customer: str,
	rtype: str,
	item: str,
	start: str,
	end: str,
	confirm: bool = True,
	contract: str | None = None,
) -> str:
	"""Create a booking on a free unit of ``item``; hold it, and confirm it when asked."""
	from frappe_rental.services import lifecycle

	doc = frappe.get_doc(
		{
			"doctype": "Rental Booking",
			"customer": customer,
			"rental_type": rtype,
			"location": LOCATION,
			"from_datetime": start,
			"to_datetime": end,
			"contract": contract,
			"lines": [{"rental_item": item}],
		}
	).insert()
	if frappe.db.get_value("Rental Type", rtype, "requires_hold"):
		lifecycle.place_hold(doc)
	if confirm:
		doc.submit()
	return doc.name


def signed_contract(customer: str, start: str) -> str:
	"""A signed ERPNext Contract for types that need one (until the Rental Contract doctype exists)."""
	doc = frappe.get_doc(
		{
			"doctype": "Contract",
			"party_type": "Customer",
			"party_name": customer,
			"start_date": start,
			"contract_terms": "Demo rental terms",
			"is_signed": 1,
			"signee": customer,
			"signed_on": now_datetime(),
		}
	)
	doc.insert()
	return doc.name


# T59: every preset ---------------------------------------------------------------------------

EXTRA_CARDS = {
	"Demo Hourly": ("Hour", 450),
	"Demo Daily": ("Day", 300),
	"Demo Nightly": ("Day", 2200),
	"Demo Monthly": ("Month", 1500),
}
# preset -> (item name, rate card, unit names, extra unit fields)
PRESET_ITEMS = {
	"Hotel Room": ("Demo Deluxe room, Zamalek", "Demo Nightly", ["Room 201", "Room 202"], {}),
	"Storage Unit": ("Demo 10 m2 storage, 6th October", "Demo Monthly", ["S-01", "S-02"], {}),
	"Event Gear": ("Demo folding chairs", "Demo Daily", ["Chair pool"], {"quantity_available": 200}),
	"Bicycle": ("Demo city bike", "Demo Daily", ["Bike pool"], {"quantity_available": 12}),
	"Boat Charter": ("Demo felucca, Nile", "Demo Hourly", ["Felucca Amira"], {}),
	"Meeting Room": ("Demo meeting room, 8 seats", "Demo Hourly", ["Room Luxor"], {}),
	"Tool": ("Demo hammer drill", "Demo Daily", ["DRILL-B1"], {"batch": True}),
	"Photographer": ("Demo event photographer", "Demo Hourly", ["Mona (photographer)"], {"provider": True}),
	"Tour Guide": ("Demo Giza tour guide", "Demo Hourly", ["Karim (guide)"], {"provider": True}),
	"Maintenance": ("Demo AC maintenance visit", "Demo Monthly", ["Technician Omar"], {"provider": True}),
	# Vehicle units are identified by an ERPNext Asset: link your own Assets to units.
	"Vehicle": ("Demo Toyota Corolla", "Demo Daily", [], {}),
}
SCHEDULE = "Demo working hours"
BATCH_ITEM = "DEMO-DRILL"
TEMPLATE = "Demo maintenance terms"


def make_full_demo(with_bookings: bool = False) -> dict:
	"""``make_demo`` plus an item (and units where they need no ERPNext asset) for every preset,
	working hours for providers, and an active maintenance contract with quarterly visits."""
	out = make_demo(with_bookings=with_bookings)
	company = frappe.db.get_value("Rental Location", LOCATION, "company")
	currency = frappe.db.get_value("Company", company, "default_currency")
	for card, (unit, rate) in EXTRA_CARDS.items():
		if not frappe.db.exists("Rental Rate Card", card):
			frappe.get_doc(
				{
					"doctype": "Rental Rate Card",
					"card_name": card,
					"currency": currency,
					"rates": [{"time_unit": unit, "rate": rate}],
				}
			).insert()
	schedule = _schedule()
	units = {}
	for rtype, (name, card, unit_names, extra) in PRESET_ITEMS.items():
		if not frappe.db.exists("Rental Type", rtype):
			continue
		item = frappe.db.get_value("Rental Item", {"item_name": name})
		if not item:
			item = (
				frappe.get_doc(
					{
						"doctype": "Rental Item",
						"item_name": name,
						"rental_type": rtype,
						"rate_card": card,
						"location": LOCATION,
						"is_published": 1,
					}
				)
				.insert()
				.name
			)
		out["items"][rtype] = item
		for unit_name in unit_names:
			existing = frappe.db.get_value("Rental Unit", {"unit_name": unit_name, "rental_item": item})
			if existing:
				units[rtype] = existing
				continue
			fields = {
				"doctype": "Rental Unit",
				"unit_name": unit_name,
				"rental_item": item,
				"location": LOCATION,
			}
			if extra.get("quantity_available"):
				fields["quantity_available"] = extra["quantity_available"]
			if extra.get("batch"):
				fields["batch_no"] = _batch(f"DEMO-{unit_name}")
			if extra.get("provider"):
				fields.update({"unit_type": "Provider", "working_hours": schedule})
			units[rtype] = frappe.get_doc(fields).insert().name
	out["units"] = units
	out["contract"] = _maintenance_contract(out["customers"][0], company)
	return out


def _schedule() -> str:
	if not frappe.db.exists("Rental Schedule", SCHEDULE):
		frappe.get_doc(
			{
				"doctype": "Rental Schedule",
				"schedule_name": SCHEDULE,
				"slot_minutes": 60,
				"slots": [
					{"weekday": d, "from_time": "09:00:00", "to_time": "17:00:00"}
					for d in ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday")
				],
			}
		).insert()
	return SCHEDULE


def _batch(batch_id: str) -> str:
	if not frappe.db.exists("Item", BATCH_ITEM):
		from frappe_rental.services.rental_item import _item_group, _stock_uom

		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": BATCH_ITEM,
				"item_name": "Demo hammer drill",
				"item_group": _item_group(),
				"stock_uom": _stock_uom(),
				"is_stock_item": 1,
				"has_batch_no": 1,
			}
		).insert()
	if not frappe.db.exists("Batch", batch_id):
		frappe.get_doc({"doctype": "Batch", "batch_id": batch_id, "item": BATCH_ITEM}).insert()
	return batch_id


def _maintenance_contract(customer: str, company: str) -> str:
	"""An active one-year AC maintenance contract with quarterly visits (once)."""
	from frappe_rental.services import contracts

	existing = frappe.db.get_value("Rental Contract", {"customer": customer, "visit_frequency": "Quarterly"})
	if existing:
		return existing
	if not frappe.db.exists("Rental Terms Template", TEMPLATE):
		frappe.get_doc(
			{
				"doctype": "Rental Terms Template",
				"template_name": TEMPLATE,
				"body": "<p>AC maintenance for {{ customer.customer_name }} from {{ contract.start_date }}.</p>",
			}
		).insert()
	start = getdate(now_datetime()).replace(day=1)
	doc = frappe.get_doc(
		{
			"doctype": "Rental Contract",
			"customer": customer,
			"company": company,
			"rental_type": "Maintenance",
			"start_date": start,
			"end_date": add_days(start.replace(year=start.year + 1), -1),
			"terms_template": TEMPLATE,
			"visit_frequency": "Quarterly",
			"sla_response_hours": 4,
			"sla_resolution_hours": 48,
			"auto_renew": 1,
			"renewal_term_months": 12,
			"notice_period_days": 30,
		}
	).insert()
	contracts.send_for_signature(doc)
	contracts.activate(doc, "Demo customer", countersigned_by="Administrator")
	return doc.name

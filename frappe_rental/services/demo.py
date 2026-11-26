"""Demo data (T21): Device and Apartment presets with items, units and customers, built in code.

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

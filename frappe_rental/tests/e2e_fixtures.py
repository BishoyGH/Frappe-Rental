"""Data for the Playwright smoke (T18). Run before the browser tests:

    bench --site <site> execute frappe_rental.tests.e2e_fixtures.setup

Idempotent: safe to run on every CI leg and locally.
"""

import frappe

from frappe_rental.compat.erpnext import ensure_setup_complete
from frappe_rental.services.setup import create_defaults
from frappe_rental.tests.utils import make_customer

TYPE, CARD, ITEM, CUSTOMER = "E2E Type", "E2E Card", "E2E Camera", "E2E Customer"
KIT_TYPE, KIT = "E2E Kit Type", "E2E Kit"
# Customer booking flow (T35): a published item and a returning customer who can sign in.
SHOP_TYPE, BIKE = "E2E Shop Type", "E2E Bike"
RETURNING_EMAIL, RETURNING_PASSWORD = "e2e-returning@example.com", "E2e-Returning-1"


def setup() -> None:
	company = ensure_setup_complete()
	create_defaults()
	currency = frappe.db.get_value("Company", company, "default_currency")
	if not frappe.db.exists("Rental Rate Card", CARD):
		frappe.get_doc(
			{
				"doctype": "Rental Rate Card",
				"card_name": CARD,
				"currency": currency,
				"rates": [{"time_unit": "Day", "rate": 100}],
			}
		).insert()
	if not frappe.db.exists("Rental Type", TYPE):
		frappe.get_doc(
			{
				"doctype": "Rental Type",
				"type_name": TYPE,
				"mode": "Resource",
				"time_unit": "Day",
				"requires_hold": 1,
			}
		).insert()
	if not frappe.db.exists("Rental Item", {"item_name": ITEM}):
		item = frappe.get_doc(
			{"doctype": "Rental Item", "item_name": ITEM, "rental_type": TYPE, "rate_card": CARD}
		).insert()
		for n in range(1, 4):
			frappe.get_doc(
				{"doctype": "Rental Unit", "unit_name": f"E2E CAM-{n:02}", "rental_item": item.name}
			).insert()
	# Handover specs (T29) use their own type and item: a damaged return blocks its unit, which
	# would change the E2E Type calendar rows.
	if not frappe.db.exists("Rental Type", KIT_TYPE):
		frappe.get_doc(
			{"doctype": "Rental Type", "type_name": KIT_TYPE, "mode": "Resource", "time_unit": "Day"}
		).insert()
	if not frappe.db.exists("Rental Item", {"item_name": KIT}):
		kit = frappe.get_doc(
			{"doctype": "Rental Item", "item_name": KIT, "rental_type": KIT_TYPE, "rate_card": CARD}
		).insert()
		for n in range(1, 11):
			frappe.get_doc(
				{"doctype": "Rental Unit", "unit_name": f"E2E KIT-{n:02}", "rental_item": kit.name}
			).insert()
	make_customer(CUSTOMER)
	_shop(currency)
	frappe.db.commit()


def _shop(currency) -> None:
	if not frappe.db.exists("Rental Type", SHOP_TYPE):
		frappe.get_doc(
			{"doctype": "Rental Type", "type_name": SHOP_TYPE, "mode": "Resource", "time_unit": "Day"}
		).insert()
	if not frappe.db.exists("Rental Charge", {"charge_name": "E2E Helmet"}):
		frappe.get_doc(
			{"doctype": "Rental Charge", "charge_name": "E2E Helmet", "charge_type": "Fixed", "amount": 5}
		).insert()
	card = "E2E Shop Card"
	if not frappe.db.exists("Rental Rate Card", card):
		helmet = frappe.db.get_value("Rental Charge", {"charge_name": "E2E Helmet"})
		frappe.get_doc(
			{
				"doctype": "Rental Rate Card",
				"card_name": card,
				"currency": currency,
				"rates": [{"time_unit": "Day", "rate": 40}],
				"charges": [{"charge": helmet, "is_mandatory": 0}],
			}
		).insert()
	if not frappe.db.exists("Rental Item", {"item_name": BIKE}):
		bike = frappe.get_doc(
			{
				"doctype": "Rental Item",
				"item_name": BIKE,
				"rental_type": SHOP_TYPE,
				"rate_card": card,
				"is_published": 1,
			}
		).insert()
		for n in range(1, 31):
			frappe.get_doc(
				{"doctype": "Rental Unit", "unit_name": f"E2E BIKE-{n:02}", "rental_item": bike.name}
			).insert()
	if not frappe.db.exists("User", RETURNING_EMAIL):
		from frappe_rental.services import checkout

		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": RETURNING_EMAIL,
				"first_name": "Robin",
				"last_name": "Returning",
				"user_type": "Website User",
				"send_welcome_email": 0,
				"new_password": RETURNING_PASSWORD,
			}
		).insert()
		checkout._new_customer("Robin Returning", user.name, RETURNING_EMAIL, None)

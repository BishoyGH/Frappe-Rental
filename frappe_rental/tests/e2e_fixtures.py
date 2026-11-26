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
	frappe.db.commit()

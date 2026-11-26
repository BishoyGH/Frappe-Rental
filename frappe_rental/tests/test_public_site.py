import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.api import public as api
from frappe_rental.compat.erpnext import ensure_setup_complete
from frappe_rental.services import public_site as svc
from frappe_rental.services.setup import create_defaults


def make(doctype, key, name, **kw):
	if not frappe.db.exists(doctype, name):
		frappe.get_doc({"doctype": doctype, key: name, **kw}).insert()
	return name


class TestPublicSite(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		company = ensure_setup_complete()
		create_defaults()
		cur = frappe.db.get_value("Company", company, "default_currency")
		make(
			"Rental Rate Card",
			"card_name",
			"T34 Card",
			currency=cur,
			rates=[{"time_unit": "Hour", "rate": 10}],
		)
		make("Rental Type", "type_name", "T34 Type", mode="Resource", time_unit="Hour")
		cls.loc = make("Rental Location", "location_name", "T34 Loc", company=company)

	def item(self, published=1):
		doc = frappe.get_doc(
			{
				"doctype": "Rental Item",
				"item_name": f"T34 {random_string(6)}",
				"rental_type": "T34 Type",
				"rate_card": "T34 Card",
				"location": self.loc,
				"is_published": published,
				"description": "<p>A <b>fine</b> thing</p>",
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Rental Unit",
				"unit_name": f"T34 {random_string(6)}",
				"rental_item": doc.name,
				"location": self.loc,
				"barcode": random_string(10),
			}
		).insert()
		return doc

	def test_lists_published_only_with_price_for_dates(self):
		pub, hidden = self.item(), self.item(published=0)
		names = [i.name for i in svc.list_items(rental_type="T34 Type")["items"]]
		self.assertIn(pub.name, names)
		self.assertNotIn(hidden.name, names)
		dated = svc.list_items(
			rental_type="T34 Type", from_datetime="2027-03-01 10:00", to_datetime="2027-03-01 12:00"
		)
		row = next(i for i in dated["items"] if i.name == pub.name)
		self.assertEqual(row["price"], 20)
		self.assertIn("T34 Type", svc.filter_options()["rental_types"])

	def test_quote_and_calendar_refuse_unpublished(self):
		hidden = self.item(published=0)
		with self.assertRaises(frappe.DoesNotExistError):
			svc.quote(hidden.name, "2027-03-01 10:00", "2027-03-01 12:00")
		with self.assertRaises(frappe.DoesNotExistError):
			svc.calendar(hidden.name, 2027, 3)

	def test_guest_quote_calendar_and_page_context(self):
		pub = self.item()
		frappe.set_user("Guest")
		try:
			q = api.quote(pub.name, "2027-03-02 10:00", "2027-03-02 13:00")
			self.assertTrue(q["available"])
			self.assertEqual(q["net_total"], 30)
			cal = api.calendar(pub.name, "2027-03")
			self.assertEqual(cal.get("2027-03-02") or next(iter(cal.values())), "free")
			with self.assertRaises(frappe.ValidationError):
				api.calendar(pub.name, "March")
		finally:
			frappe.set_user("Administrator")
		ctx = svc.item_context(pub)
		self.assertEqual(ctx["from_rate"]["rate"], 10)
		self.assertEqual(ctx["metatags"]["description"], "A fine thing")

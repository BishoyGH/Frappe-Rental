import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime, random_string

from frappe_rental.api import booking as api
from frappe_rental.compat.erpnext import ensure_setup_complete
from frappe_rental.services import lifecycle
from frappe_rental.services.availability import UnavailableError
from frappe_rental.services.setup import create_defaults
from frappe_rental.tests.utils import make_customer

CACHE = "Rental Availability Cache"


def make_type(name, **kw):
	if not frappe.db.exists("Rental Type", name):
		frappe.get_doc(
			{"doctype": "Rental Type", "type_name": name, "mode": "Resource", "time_unit": "Day", **kw}
		).insert()
	return name


class TestLifecycle(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		company = ensure_setup_complete()
		create_defaults()
		currency = frappe.db.get_value("Company", company, "default_currency")
		if not frappe.db.exists("Rental Rate Card", "T14 Card"):
			frappe.get_doc(
				{
					"doctype": "Rental Rate Card",
					"card_name": "T14 Card",
					"currency": currency,
					"rates": [{"time_unit": "Day", "rate": 100}],
				}
			).insert()
		if not frappe.db.exists("Rental Deposit Rule", "T14 Deposit"):
			frappe.get_doc(
				{"doctype": "Rental Deposit Rule", "rule_name": "T14 Deposit", "percent": 10}
			).insert()
		make_type("T14 Plain", requires_hold=0)
		make_type("T14 Held", requires_hold=1)
		make_type("T14 Deposit", requires_hold=0, requires_deposit=1, deposit_rule="T14 Deposit")
		make_type("T14 Contract", requires_hold=0, requires_contract=1)
		cls.customer = make_customer()

	def booking(self, rtype="T14 Plain", start="2026-05-01 10:00", end="2026-05-03 10:00", unit=True):
		item = frappe.get_doc(
			{
				"doctype": "Rental Item",
				"item_name": f"T14 {random_string(6)}",
				"rental_type": rtype,
				"rate_card": "T14 Card",
			}
		).insert()
		unit_name = None
		if unit:
			unit_name = (
				frappe.get_doc(
					{
						"doctype": "Rental Unit",
						"unit_name": f"T14 {random_string(6)}",
						"rental_item": item.name,
					}
				)
				.insert()
				.name
			)
		return frappe.get_doc(
			{
				"doctype": "Rental Booking",
				"customer": self.customer,
				"rental_type": rtype,
				"from_datetime": start,
				"to_datetime": end,
				"lines": [{"rental_item": item.name, "rental_unit": unit_name}],
			}
		).insert()

	def rows(self, doc):
		return frappe.db.count(CACHE, {"source_doctype": "Rental Booking", "source_name": doc.name})

	def twin(self, doc):
		"""Another draft booking for the same unit and period."""
		other = frappe.copy_doc(doc)
		other.status = "Draft"
		other.insert()
		return other

	def test_draft_holds_nothing(self):
		doc = self.booking()
		self.assertEqual(doc.status, "Draft")
		self.assertEqual(self.rows(doc), 0)

	def test_hold_reserves_and_blocks_others(self):
		doc = self.booking()
		state = api.create_hold(doc.name)
		self.assertEqual(state["status"], "Hold")
		self.assertTrue(state["hold_expires_on"])
		self.assertEqual(self.rows(doc), 1)
		other = self.twin(doc)
		with self.assertRaises(UnavailableError):
			lifecycle.place_hold(other)

	def test_hold_reserves_again_on_edit(self):
		doc = self.booking()
		lifecycle.place_hold(doc)
		doc.to_datetime = "2026-05-05 10:00"
		doc.save()
		row = frappe.get_all(CACHE, filters={"source_name": doc.name}, fields=["busy_to"])
		self.assertEqual(len(row), 1)
		self.assertEqual(str(row[0].busy_to), "2026-05-05 10:00:00")

	def test_hold_expiry_releases_units(self):
		doc = self.booking()
		lifecycle.place_hold(doc)
		self.assertNotIn(doc.name, lifecycle.expire_holds())  # not yet expired
		expired = lifecycle.expire_holds(
			now=add_to_date(now_datetime(), minutes=lifecycle.hold_minutes() + 1)
		)
		self.assertIn(doc.name, expired)
		doc.reload()
		self.assertEqual(doc.status, "Draft")
		self.assertIsNone(doc.hold_expires_on)
		self.assertEqual(self.rows(doc), 0)
		self.assertNotIn(doc.name, lifecycle.expire_holds(now=add_to_date(now_datetime(), days=1)))
		lifecycle.place_hold(self.twin(doc))  # unit is free again

	def test_expired_hold_cannot_confirm(self):
		doc = self.booking()
		lifecycle.place_hold(doc)
		frappe.db.set_value(
			"Rental Booking", doc.name, "hold_expires_on", add_to_date(now_datetime(), minutes=-1)
		)
		doc.reload()
		with self.assertRaises(frappe.ValidationError):
			doc.submit()

	def test_confirm_from_hold(self):
		doc = self.booking()
		lifecycle.place_hold(doc)
		state = api.confirm(doc.name)
		self.assertEqual(state["status"], "Confirmed")
		self.assertIsNone(state["hold_expires_on"])
		self.assertEqual(self.rows(doc), 1)
		self.assertEqual(lifecycle.expire_holds(now=add_to_date(now_datetime(), days=1)).count(doc.name), 0)

	def test_confirm_draft_assigns_unit(self):
		doc = self.booking(unit=False)
		unit = frappe.get_doc(
			{
				"doctype": "Rental Unit",
				"unit_name": f"T14 {random_string(6)}",
				"rental_item": doc.lines[0].rental_item,
			}
		).insert()
		doc.reload()
		doc.submit()
		self.assertEqual(
			frappe.db.get_value("Rental Booking Line", doc.lines[0].name, "rental_unit"), unit.name
		)
		self.assertEqual(doc.status, "Confirmed")

	def test_confirm_clash_rejected(self):
		doc = self.booking()
		other = self.twin(doc)
		doc.submit()
		with self.assertRaises(UnavailableError):
			other.submit()

	def test_requires_hold(self):
		doc = self.booking("T14 Held")
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		doc.reload()
		lifecycle.place_hold(doc)
		doc.submit()
		self.assertEqual(doc.status, "Confirmed")

	def test_requires_deposit(self):
		doc = self.booking("T14 Deposit")
		self.assertGreater(doc.deposit_required, 0)
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		doc.reload()
		doc.db_set("deposit_paid", doc.deposit_required)
		doc.submit()
		self.assertEqual(doc.status, "Confirmed")

	def test_requires_signed_contract(self):
		doc = self.booking("T14 Contract")
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		contract = frappe.get_doc(
			{
				"doctype": "Contract",
				"party_type": "Customer",
				"party_name": self.customer,
				"start_date": "2026-05-01",
				"contract_terms": "Terms",
			}
		).insert()
		doc.reload()
		doc.contract = contract.name
		doc.save()
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		contract.reload()
		contract.is_signed = 1
		contract.signee = "Test Signee"
		contract.signed_on = now_datetime()  # required on v16
		contract.save()
		doc.reload()
		doc.submit()
		self.assertEqual(doc.status, "Confirmed")

	def test_cancel_confirmed_frees_units(self):
		doc = self.booking()
		other = self.twin(doc)
		doc.submit()
		state = api.cancel(doc.name)
		self.assertEqual(state["status"], "Cancelled")
		self.assertEqual(frappe.db.get_value("Rental Booking", doc.name, "docstatus"), 2)
		self.assertEqual(self.rows(doc), 0)
		other.submit()
		lifecycle.cancel(frappe.get_doc("Rental Booking", other.name))  # cancel via service too
		self.assertEqual(self.rows(other), 0)

	def test_cancel_hold_frees_units(self):
		doc = self.booking()
		lifecycle.place_hold(doc)
		api.cancel(doc.name)
		doc.reload()
		self.assertEqual(doc.status, "Cancelled")
		self.assertEqual(self.rows(doc), 0)
		with self.assertRaises(frappe.ValidationError):
			lifecycle.place_hold(doc)
		with self.assertRaises(frappe.ValidationError):
			lifecycle.cancel(self.booking())  # plain draft

	def test_delete_draft_releases(self):
		doc = self.booking()
		lifecycle.place_hold(doc)
		doc.delete()
		self.assertEqual(self.rows(doc), 0)

	def test_api_permissions(self):
		doc = self.booking()
		frappe.set_user("Guest")
		try:
			for fn in (api.create_hold, api.confirm, api.cancel):
				with self.assertRaises(frappe.PermissionError):
					fn(doc.name)
		finally:
			frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError):
			api.create_hold("")

	def test_scheduler_hook(self):
		hooks = frappe.get_hooks("scheduler_events")["cron"]["*/5 * * * *"]
		self.assertIn("frappe_rental.services.lifecycle.expire_holds", hooks)

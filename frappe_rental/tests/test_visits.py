"""Maintenance visits (T46): quarterly HVAC plan, technician booking, completion, SLA and renewal."""

import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_rental.services import contracts, renewal, visits
from frappe_rental.tests import test_erpnext_sync as t16
from frappe_rental.tests import test_provider as t45
from frappe_rental.tests.test_contracts import make_contract

P = t45.TestProvider.__dict__


class TestVisits(FrappeTestCase):
	_tax_template = t16.TestErpnextSync.__dict__["_tax_template"]
	make_fixtures = t16.TestErpnextSync.__dict__["make_fixtures"]
	_unit = P["_unit"]
	provider_unit = P["provider_unit"]

	@classmethod
	def setUpClass(cls):
		P["setUpClass"].__func__(cls)

	def hvac(self, **kw):
		doc = make_contract(visit_frequency="Quarterly", sla_response_hours=4, sla_resolution_hours=24, **kw)
		contracts.send_for_signature(doc)
		contracts.activate(doc, "Jane")
		doc.reload()
		return doc

	def test_plan_dates(self):
		self.assertEqual(
			[str(d) for d in visits.plan_dates("2026-01-31", "2026-12-31", "Quarterly")],
			["2026-01-31", "2026-04-30", "2026-07-31", "2026-10-31"],
		)
		self.assertEqual(visits.plan_dates("2026-01-01", "2026-12-31", ""), [])

	def test_quarterly_hvac_scenario(self):
		doc = self.hvac()
		self.assertEqual(
			[str(v.planned_date) for v in doc.visits],
			["2026-01-01", "2026-04-01", "2026-07-01", "2026-10-01"],
		)
		self.assertEqual(visits.generate(doc), 0)  # idempotent

		tech = self.provider_unit()
		second = doc.visits[1].name
		booking = visits.assign(doc, second, tech, "2026-04-06 09:00", hours=2)  # a Monday
		doc.reload()
		row = next(v for v in doc.visits if v.name == second)
		self.assertEqual((row.status, row.technician, row.rental_booking), ("Booked", tech, booking))
		self.assertEqual(frappe.db.get_value("Rental Booking", booking, "rental_contract"), doc.name)
		self.assertTrue(frappe.db.exists("Project", {"rental_booking": booking}))

		visits.complete(doc, second, "Filters replaced")
		doc.reload()
		row = next(v for v in doc.visits if v.name == second)
		self.assertEqual(row.status, "Done")
		self.assertFalse(row.sla_breached)
		with self.assertRaises(frappe.ValidationError):
			visits.complete(doc, second)

	def test_assign_needs_provider_in_hours(self):
		doc = self.hvac()
		with self.assertRaises(frappe.ValidationError):
			visits.assign(doc, doc.visits[0].name, self._unit(), "2026-04-06 09:00")
		with self.assertRaises(frappe.ValidationError):
			visits.assign(doc, doc.visits[0].name, self.provider_unit(), "2026-04-07 09:00")  # Tuesday

	def test_service_request_sla(self):
		doc = self.hvac()
		name = visits.request_service(doc, "No cooling", now="2026-05-04 08:00")
		doc.reload()
		row = next(v for v in doc.visits if v.name == name)
		self.assertEqual(str(row.response_due), "2026-05-04 12:00:00")
		self.assertEqual(str(row.resolution_due), "2026-05-05 08:00:00")
		visits.check_sla(now="2026-05-04 11:00")
		self.assertFalse(frappe.db.get_value("Rental Contract Visit", name, "sla_breached"))
		visits.check_sla(now="2026-05-04 13:00")
		self.assertTrue(frappe.db.get_value("Rental Contract Visit", name, "sla_breached"))
		self.assertEqual(frappe.db.get_value("Rental Contract Visit", name, "status"), "Planned")

	def test_missed_visits_flagged(self):
		doc = self.hvac()
		visits.check_sla(now="2026-01-03 09:00")
		self.assertEqual(frappe.db.get_value("Rental Contract Visit", doc.visits[0].name, "status"), "Missed")
		self.assertEqual(
			frappe.db.get_value("Rental Contract Visit", doc.visits[1].name, "status"), "Planned"
		)

	def test_renewal_plans_its_own_visits(self):
		doc = self.hvac(auto_renew=1, renewal_term_months=12, notice_period_days=30)
		new = frappe.get_doc("Rental Contract", renewal.renew(doc))
		self.assertEqual(new.status, "Active")
		self.assertEqual(
			[str(v.planned_date) for v in new.visits],
			["2027-01-01", "2027-04-01", "2027-07-01", "2027-10-01"],
		)
		self.assertTrue(all(v.status == "Planned" for v in new.visits))

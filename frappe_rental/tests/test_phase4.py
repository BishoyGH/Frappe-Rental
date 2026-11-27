"""Phase 4 acceptance (T48): contract scenarios end to end.

1. A 12-month device contract billed quarterly, with a unit swap half way.
2. A photographer retainer: provider hours drawn from a contract allowance, overage billed.
3. A maintenance plan with quarterly visits that renews with indexation.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, random_string

from frappe_rental.services import allocations, availability, calloff, contracts, invoicing, renewal, visits
from frappe_rental.tests import test_erpnext_sync as t16
from frappe_rental.tests import test_provider as t45
from frappe_rental.tests.test_contracts import make_contract

QUARTERLY = {"frequency": "Quarterly", "alignment": "Rental anniversary", "timing": "In advance"}


class TestPhase4(FrappeTestCase):
	_tax_template = t16.TestErpnextSync.__dict__["_tax_template"]
	make_fixtures = t16.TestErpnextSync.__dict__["make_fixtures"]
	_unit = t45.TestProvider.__dict__["_unit"]
	provider_unit = t45.TestProvider.__dict__["provider_unit"]

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()
		t45.make_hourly_fixtures(cls.company)

	def active(self, **kw):
		doc = make_contract(customer=self.customer, **kw)
		contracts.send_for_signature(doc)
		contracts.activate(doc, "Jane", countersigned_by="Administrator")
		doc.reload()
		return doc

	def device(self):
		item = frappe.get_doc(
			{
				"doctype": "Rental Item",
				"item_name": f"T48 {random_string(6)}",
				"rental_type": "T16 Device",
				"rate_card": "T16 Card",
			}
		).insert()
		return (
			frappe.get_doc(
				{"doctype": "Rental Unit", "unit_name": f"T48 {random_string(6)}", "rental_item": item.name}
			)
			.insert()
			.name
		)

	def booking(self, contract, row, unit, start, end):
		return frappe.get_doc(
			{
				"doctype": "Rental Booking",
				"customer": self.customer,
				"rental_type": frappe.db.get_value(
					"Rental Item", frappe.db.get_value("Rental Unit", unit, "rental_item"), "rental_type"
				),
				"company": self.company,
				"from_datetime": start,
				"to_datetime": end,
				"rental_contract": contract.name,
				"contract_allocation": row,
				"lines": [
					{
						"rental_item": frappe.db.get_value("Rental Unit", unit, "rental_item"),
						"rental_unit": unit,
						"qty": 1,
					}
				],
			}
		).insert()

	def test_device_year_quarterly_billing_with_swap(self):
		old, new = self.device(), self.device()
		contract = self.active(
			allocations=[{"allocation_type": "Specific unit", "rental_unit": old, "rate_override": 10}],
			billing_plan=[QUARTERLY],
		)
		row = contract.allocations[0].name
		booking = self.booking(contract, row, old, "2026-01-01 00:00", "2026-12-31 23:00")
		booking.submit()
		booking.reload()
		net = flt(booking.net_total, 2)
		self.assertEqual(flt(booking.lines[0].rate), 10)  # contract rate
		self.assertEqual(len(booking.billing_schedule), 4)
		self.assertEqual(flt(sum(flt(r.amount) for r in booking.billing_schedule), 2), net)

		allocations.swap(contract, row, new, "2026-07-01", "Battery failure")
		self.assertFalse(availability.is_available(new, "2026-08-01 10:00", "2026-08-02 10:00"))

		invoicing.run_due_invoices("2026-12-31")
		invoicing.run_due_invoices("2026-12-31")  # rerun bills nothing twice
		invoices = frappe.get_all(
			"Sales Invoice",
			filters={"rental_booking": booking.name, "docstatus": 1, "is_return": 0},
			pluck="net_total",
		)
		self.assertEqual(len(invoices), 4)
		self.assertEqual(flt(sum(flt(v) for v in invoices), 2), net)

	def test_photographer_retainer_with_overage(self):
		photographer = self.provider_unit()
		contract = self.active(
			allocations=[{"allocation_type": "Provider time", "rental_unit": photographer, "capacity": 5}],
			overage_rate=80,
		)
		row = contract.allocations[0].name
		first = self.booking(contract, row, photographer, "2026-03-02 09:00", "2026-03-02 12:00")
		first.submit()
		self.assertEqual(calloff.remaining(contract.name, row), 2)
		second = self.booking(contract, row, photographer, "2026-03-09 13:00", "2026-03-09 17:00")
		second.submit()
		self.assertEqual(calloff.remaining(contract.name, row), -2)
		overage = frappe.get_all(
			"Rental Billable Event", filters={"rental_booking": second.name}, pluck="amount"
		)
		self.assertEqual([flt(a) for a in overage], [160])
		self.assertTrue(frappe.db.exists("Project", {"rental_booking": second.name}))
		with self.assertRaises(availability.UnavailableError):
			self.booking(contract, row, photographer, "2026-03-10 10:00", "2026-03-10 11:00")  # Tuesday

		first.cancel()
		self.assertEqual(calloff.remaining(contract.name, row), 1)

	def test_maintenance_plan_renewal(self):
		technician = self.provider_unit()
		contract = self.active(
			visit_frequency="Quarterly",
			sla_response_hours=4,
			sla_resolution_hours=48,
			auto_renew=1,
			renewal_term_months=12,
			notice_period_days=30,
			indexation_percent=5,
			billing_plan=[{**QUARTERLY, "amount_basis": "Fixed amount per period", "period_amount": 300}],
		)
		self.assertEqual(len(contract.visits), 4)
		visit = contract.visits[1].name
		visits.assign(contract, visit, technician, "2026-04-06 09:00")
		visits.complete(contract, visit, "Serviced")

		result = renewal.renew(contract)
		contract.reload()
		self.assertEqual(contract.status, "Renewed")
		new = frappe.get_doc("Rental Contract", result)
		self.assertEqual(
			(new.status, str(new.start_date), str(new.end_date)), ("Active", "2027-01-01", "2027-12-31")
		)
		self.assertEqual(flt(new.billing_plan[0].period_amount), 315)
		self.assertEqual(
			[str(v.planned_date)[:7] for v in new.visits], ["2027-01", "2027-04", "2027-07", "2027-10"]
		)
		self.assertEqual(renewal.renew(contract), result)  # idempotent

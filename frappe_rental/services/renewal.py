"""Renewal and termination (T44, D7 lifecycle): notice, auto-renew with indexation, ending, fees.

Daily `run(today)`:
1. Notice: when `today` reaches end - notice_period_days, emit `contract_notice` once per term; a
   contract that does not auto-renew moves to Ending.
2. Expiry: after the end date an auto-renewing contract is renewed (`renew`), any other one Ends;
   both release the old term's allocations, and Ended contracts emit `contract_ended`.
`renew` copies the contract into the next term (`renewal_of`), raises rates by `indexation_percent`
(allocation rate overrides and the billing plan's period amount), keeps the signed terms text and
the signature (the original agreement allows the renewal), re-reserves allocations and emits
`contract_renewed`.
`terminate` records the reason and charges `early_termination_fee` as a contract-level Billable
Event when it ends before the minimum term (or always, when no minimum term is set).
`closure_checklist` lists what is still open: units out, planned billing rows, deposits held and
pending charges.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, getdate, nowdate

from frappe_rental.services import allocations, billable_events, contracts, events
from frappe_rental.services.handover import units_out

RUNNING = ("Active", "Ending")


def run(today=None) -> dict:
	today = getdate(today or nowdate())
	done = {"notice": [], "renewed": [], "ended": []}
	for name in frappe.get_all(
		"Rental Contract",
		filters={"status": ["in", RUNNING], "open_ended": 0},
		pluck="name",
		order_by="end_date",
	):
		doc = frappe.get_doc("Rental Contract", name)
		end = getdate(doc.end_date)
		if today > end:
			if doc.auto_renew:
				done["renewed"].append(renew(doc))
			else:
				_end(doc)
				done["ended"].append(name)
			continue
		if doc.notice_period_days and today >= add_days(end, -doc.notice_period_days):
			if events.emit("contract_notice", doc, key=str(end)):
				done["notice"].append(name)
			if not doc.auto_renew and doc.status == "Active":
				contracts.transition(doc, "Ending")
	return done


def _end(doc) -> None:
	if doc.status == "Active":
		contracts.transition(doc, "Ending")
	allocations.release_all(doc)
	contracts.transition(doc, "Ended")
	events.emit("contract_ended", doc)


def renew(doc) -> str:
	"""Create the next term. Safe to run twice: an existing renewal is returned."""
	existing = frappe.db.get_value("Rental Contract", {"renewal_of": doc.name})
	if existing:
		return existing
	factor = 1 + flt(doc.indexation_percent) / 100
	start = add_days(doc.end_date, 1)
	new = frappe.copy_doc(doc)
	new.update(
		{
			"renewal_of": doc.name,
			"start_date": start,
			"end_date": add_days(add_months(start, doc.renewal_term_months or 12), -1),
			"status": "Draft",
			"erpnext_contract": None,
			"amendments": [],
			"terminated_on": None,
			"termination_reason": None,
		}
	)
	for row in new.allocations:
		row.from_date, row.to_date = None, None
		row.capacity_used = 0
		if flt(row.rate_override):
			row.rate_override = flt(row.rate_override * factor, 2)
	new.allocations = [r for r in new.allocations if r.status in ("Reserved", "Active")]
	for row in new.billing_plan:
		if flt(row.period_amount):
			row.period_amount = flt(row.period_amount * factor, 2)
	new.flags.ignore_permissions = True  # renewal allowed by the signed agreement
	new.insert()
	allocations.release_all(doc)
	doc.flags.amending = True
	if doc.status == "Active":
		contracts.transition(doc, "Ending")
	contracts.transition(doc, "Renewed")
	# carry the signature: the renewal clause of the signed agreement covers the new term
	new.db_set({"status": "Awaiting Signature", "signed_by": doc.signed_by, "signed_on": doc.signed_on})
	new.reload()
	contracts.activate(new, doc.signed_by, countersigned_by=doc.countersigned_by)
	events.emit("contract_renewed", new)
	return new.name


def terminate(doc, reason: str, on=None) -> str | None:
	"""Terminate early and charge the fee. Returns the fee event, if any."""
	on = getdate(on or nowdate())
	event = None
	if flt(doc.early_termination_fee):
		min_end = add_months(doc.start_date, doc.minimum_term_months) if doc.minimum_term_months else None
		if not min_end or on < getdate(min_end):
			event = billable_events.add(
				None,
				"Termination fee",
				doc.early_termination_fee,
				description=_("Early termination of {0}").format(doc.name),
				source=doc,
				event_date=on,
				contract=doc.name,
			)
	contracts.terminate(doc, reason, on)
	return event


def bookings(contract: str) -> list[str]:
	return frappe.get_all(
		"Rental Booking", filters={"rental_contract": contract, "docstatus": 1}, pluck="name"
	)


def closure_checklist(doc) -> dict:
	names = bookings(doc.name)
	return {
		"units_out": sorted({u for b in names for u in units_out(b)}),
		"planned_billing_rows": frappe.db.count(
			"Rental Billing Schedule",
			{"parenttype": "Rental Booking", "parent": ["in", names or [""]], "status": "Planned"},
		),
		"deposits_held": [
			d.name
			for d in frappe.get_all(
				"Rental Deposit",
				filters={"rental_booking": ["in", names or [""]]},
				fields=["name", "balance_held"],
			)
			if flt(d.balance_held) > 0
		],
		"pending_charges": sorted(
			set(
				frappe.get_all(
					"Rental Billable Event",
					filters={"status": "Pending", "rental_contract": doc.name},
					pluck="name",
				)
			)
			| set(
				frappe.get_all(
					"Rental Billable Event",
					filters={"status": "Pending", "rental_booking": ["in", names or [""]]},
					pluck="name",
				)
			)
		),
	}

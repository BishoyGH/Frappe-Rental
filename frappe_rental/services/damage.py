"""Damage reports (T28): report, estimate, approve, settle; Asset Repair link and auto Rental Block.

Flow: Reported -> Estimated (estimate set) -> Approved (`approve`) -> Settled or Written Off.
Settlement paths (each runs once; a settled report cannot be settled again):
- Deposit:   `deposits.apply` to Damage Recovery (Journal Entry: Dr Customer Deposits, Cr Damage Recovery)
- Invoice:   a Damage Billable Event (T24), billed now on its own invoice on Damage Recovery
- Write-off: nothing is charged; the repair cost stays on the asset (no GL entry)
A report with `block_unit` adds an open-ended Rental Block (Maintenance) so the unit cannot be booked;
setting `repaired_on` ends the block. Returns with Damaged or Missing lines raise a report each.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, nowdate

from frappe_rental.compat import erpnext as compat
from frappe_rental.services import billable_events, deposits, events, invoicing

DOCTYPE = "Rental Damage Report"


def validate(doc) -> None:
	booked = frappe.db.exists(
		"Rental Booking Line", {"parent": doc.rental_booking, "rental_unit": doc.rental_unit}
	)
	if not booked:
		frappe.throw(_("{0} is not on booking {1}").format(doc.rental_unit, doc.rental_booking))
	if flt(doc.estimate_amount) < 0:
		frappe.throw(_("The estimate cannot be negative"))
	if doc.status == "Reported" and flt(doc.estimate_amount):
		doc.status = "Estimated"


def after_insert(doc) -> None:
	if doc.block_unit and not doc.rental_block:
		block = frappe.get_doc(
			{
				"doctype": "Rental Block",
				"rental_unit": doc.rental_unit,
				"reason": "Maintenance",
				"from_datetime": now_datetime(),
				"notes": _("Damage report {0}").format(doc.name),
			}
		)
		block.flags.ignore_permissions = True  # follows a permitted damage report
		block.insert()
		doc.db_set("rental_block", block.name)
	frappe.db.set_value("Rental Unit", doc.rental_unit, "status", "Maintenance")
	events.emit("damage_reported", doc)


def on_update(doc) -> None:
	if doc.repaired_on and doc.rental_block:
		block = frappe.get_doc("Rental Block", doc.rental_block)
		if not block.to_datetime or get_datetime(block.to_datetime) != get_datetime(doc.repaired_on):
			block.to_datetime = doc.repaired_on
			block.flags.ignore_permissions = True
			block.save()
		frappe.db.set_value("Rental Unit", doc.rental_unit, "status", "Available")


def from_return(handover) -> list[str]:
	"""One report per Damaged or Missing line of a submitted return. Safe to run twice."""
	made = []
	for line in handover.lines:
		if line.condition == "Good":
			continue
		name = frappe.db.get_value(
			DOCTYPE, {"rental_handover": handover.name, "rental_unit": line.rental_unit}
		)
		if not name:
			doc = frappe.get_doc(
				{
					"doctype": DOCTYPE,
					"rental_booking": handover.rental_booking,
					"rental_unit": line.rental_unit,
					"rental_handover": handover.name,
					"description": line.notes or _("{0} at return").format(_(line.condition)),
					"photo": line.photo,
				}
			)
			doc.flags.ignore_permissions = True  # raised by a permitted return
			doc.insert()
			name = doc.name
		made.append(name)
	return made


def approve(name: str, amount=None) -> None:
	doc = _lock(name)
	if doc.status not in ("Reported", "Estimated", "Approved"):
		frappe.throw(_("{0} is already {1}").format(doc.name, doc.status))
	amount = flt(doc.estimate_amount if amount is None else amount)
	if amount <= 0:
		frappe.throw(_("Approve an amount above zero, or write the damage off"))
	doc.approved_amount = amount
	doc.approved_by = frappe.session.user
	doc.status = "Approved"
	doc.flags.ignore_permissions = True
	doc.save()


def settle(name: str, method: str) -> str | None:
	"""Settle an approved report by Deposit, Invoice or Write-off. Returns the posted document."""
	doc = _lock(name)
	if doc.status in ("Settled", "Written Off"):
		frappe.throw(_("{0} is already {1}").format(doc.name, doc.status))
	if method == "Write-off":
		doc.update({"status": "Written Off", "settlement": method})
		posted = None
	else:
		if doc.status != "Approved":
			frappe.throw(_("Approve {0} before settling it").format(doc.name))
		amount = flt(doc.approved_amount)
		if method == "Deposit":
			deposit = frappe.db.get_value("Rental Deposit", {"rental_booking": doc.rental_booking})
			if not deposit:
				frappe.throw(_("Booking {0} has no deposit").format(doc.rental_booking))
			posted = deposits.apply(
				deposit,
				amount,
				income_account=frappe.db.get_single_value("Rental Settings", "damage_recovery_account"),
			)
			doc.journal_entry = posted
		elif method == "Invoice":
			event = billable_events.add(
				doc.rental_booking, "Damage", amount, description=doc.description, source=doc
			)
			doc.billable_event = event
			posted = invoicing.invoice_events(frappe.get_doc("Rental Booking", doc.rental_booking), nowdate())
		else:
			frappe.throw(_("Settle by Deposit, Invoice or Write-off"))
		doc.update({"status": "Settled", "settlement": method})
	doc.flags.ignore_permissions = True
	doc.save()
	return posted


def make_asset_repair(name: str) -> str:
	doc = frappe.get_doc(DOCTYPE, name)
	if doc.asset_repair:
		return doc.asset_repair
	asset = frappe.db.get_value("Rental Unit", doc.rental_unit, "asset")
	if not asset:
		frappe.throw(_("{0} has no asset").format(doc.rental_unit))
	repair = compat.make_asset_repair(asset, doc.company, doc.description, doc.reported_on)
	doc.db_set("asset_repair", repair)
	return repair


def _lock(name: str):
	frappe.db.sql(f"select name from `tab{DOCTYPE}` where name=%s for update", name)
	return frappe.get_doc(DOCTYPE, name)

"""Rental deposits (T25, D5.2 and D5.3). Deposits are a liability, never income, until settled.

Every money movement is a Journal Entry tagged with `rental_deposit` and listed on the deposit:

- collect:  Dr cash/bank            Cr Customer Deposits (Rental)
- refund:   Dr Customer Deposits    Cr cash/bank
- apply:    Dr Customer Deposits    Cr an income account (late fee, damage recovery) or the
            customer's receivable against a Sales Invoice
- forfeit:  Dr Customer Deposits    Cr Deposit Forfeiture Income

Journal Entries are used instead of Payment Entry so the liability account needs no party type
(Payment Entry wants a receivable or payable account for a Customer, and its advance-account options
differ between ERPNext v15 and v16; see D-deposit-journal in docs/DECISIONS.md). Every call checks
the held balance under a row lock, so two settlements cannot spend the same money.
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from frappe_rental.services import events

DOCTYPE = "Rental Deposit"


def request(booking) -> str | None:
	"""Create the booking's deposit request once (status Requested). None if no deposit is due."""
	if not flt(booking.deposit_required):
		return None
	name = frappe.db.get_value(DOCTYPE, {"rental_booking": booking.name})
	if name:
		if frappe.db.get_value(DOCTYPE, name, "status") in ("Requested", "Partly Received"):
			frappe.db.set_value(DOCTYPE, name, "amount_required", flt(booking.deposit_required))
		return name
	refundable = 1
	rule = frappe.db.get_value("Rental Type", booking.rental_type, "deposit_rule")
	if rule:
		refundable = frappe.db.get_value("Rental Deposit Rule", rule, "refundable")
		refundable = 1 if refundable is None else refundable
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"rental_booking": booking.name,
			"amount_required": flt(booking.deposit_required),
			"liability_account": liability_account(booking, required=False),
			"refundable": refundable,
		}
	)
	doc.flags.ignore_permissions = True  # made by the permitted hold or confirm of the booking
	doc.insert()
	events.emit("deposit_requested", doc)
	return doc.name


def liability_account(booking, required: bool = True) -> str | None:
	account = None
	rule = frappe.db.get_value("Rental Type", booking.rental_type, "deposit_rule")
	if rule:
		account = frappe.db.get_value("Rental Deposit Rule", rule, "liability_account")
	account = account or frappe.db.get_single_value("Rental Settings", "deposit_liability_account")
	if account and frappe.db.get_value("Account", account, "company") == booking.company:
		return account
	if required:
		frappe.throw(_("Set a deposit liability account for {0} in Rental Settings").format(booking.company))
	return None


def collect(
	deposit: str, amount, cash_account: str | None = None, mode_of_payment=None, reference=None
) -> str:
	"""Receive money into the deposit. Returns the Journal Entry."""
	doc = _lock(deposit)
	amount = _positive(amount)
	if not doc.liability_account:
		doc.liability_account = liability_account(frappe.get_doc("Rental Booking", doc.rental_booking))
	cash = _cash_account(doc.company, cash_account, mode_of_payment)
	je = _journal(
		doc, [(cash, amount, 0, None), (doc.liability_account, 0, amount, None)], "Collect", reference
	)
	doc.amount_received = flt(doc.amount_received) + amount
	_finish(doc, "Collect", amount, je)
	if flt(doc.amount_received) >= flt(doc.amount_required):
		events.emit("deposit_received", doc)
	return je


def refund(deposit: str, amount=None, cash_account: str | None = None, mode_of_payment=None) -> str:
	"""Pay back part or all (default) of the held balance."""
	doc = _lock(deposit)
	if not doc.refundable:
		frappe.throw(_("Deposit {0} is not refundable; forfeit it instead").format(doc.name))
	amount = _within_balance(doc, amount)
	cash = _cash_account(doc.company, cash_account, mode_of_payment)
	je = _journal(doc, [(doc.liability_account, amount, 0, None), (cash, 0, amount, None)], "Refund")
	doc.amount_refunded = flt(doc.amount_refunded) + amount
	_finish(doc, "Refund", amount, je)
	return je


def apply(deposit: str, amount, income_account: str | None = None, sales_invoice: str | None = None) -> str:
	"""Use held money for charges: to an income account, or against an unpaid Sales Invoice."""
	doc = _lock(deposit)
	amount = _within_balance(doc, amount)
	if sales_invoice:
		si = frappe.db.get_value(
			"Sales Invoice",
			sales_invoice,
			["debit_to", "customer", "outstanding_amount", "docstatus"],
			as_dict=True,
		)
		if not si or si.docstatus != 1 or si.customer != doc.customer:
			frappe.throw(_("Apply the deposit to a submitted invoice of {0}").format(doc.customer))
		if amount > flt(si.outstanding_amount):
			frappe.throw(_("{0} is more than the {1} outstanding").format(amount, si.outstanding_amount))
		credit = (
			si.debit_to,
			0,
			amount,
			{
				"party_type": "Customer",
				"party": doc.customer,
				"reference_type": "Sales Invoice",
				"reference_name": sales_invoice,
			},
		)
	else:
		account = income_account or frappe.db.get_single_value("Rental Settings", "damage_recovery_account")
		if not account:
			frappe.throw(_("Choose the income account the deposit is applied to"))
		credit = (account, 0, amount, None)
	je = _journal(doc, [(doc.liability_account, amount, 0, None), credit], "Apply")
	doc.amount_applied = flt(doc.amount_applied) + amount
	_finish(doc, "Apply", amount, je)
	return je


def forfeit(deposit: str, amount=None) -> str:
	"""Keep part or all (default) of the held balance as income."""
	doc = _lock(deposit)
	amount = _within_balance(doc, amount)
	account = frappe.db.get_single_value("Rental Settings", "deposit_forfeiture_income_account")
	if not account:
		frappe.throw(_("Set the Deposit Forfeiture Income account in Rental Settings"))
	je = _journal(doc, [(doc.liability_account, amount, 0, None), (account, 0, amount, None)], "Forfeit")
	doc.amount_forfeited = flt(doc.amount_forfeited) + amount
	_finish(doc, "Forfeit", amount, je)
	return je


def held(doc) -> float:
	return flt(
		flt(doc.amount_received)
		- flt(doc.amount_applied)
		- flt(doc.amount_refunded)
		- flt(doc.amount_forfeited),
		_precision(),
	)


def _precision() -> int:
	return frappe.get_precision(DOCTYPE, "amount_received") or 2


def _lock(name: str):
	frappe.db.sql(f"select name from `tab{DOCTYPE}` where name=%s for update", name)
	return frappe.get_doc(DOCTYPE, name)


def _positive(amount) -> float:
	amount = flt(amount, _precision())
	if amount <= 0:
		frappe.throw(_("Amount must be more than zero"))
	return amount


def _within_balance(doc, amount) -> float:
	balance = held(doc)
	amount = balance if amount is None else _positive(amount)
	if amount <= 0 or amount > balance:
		frappe.throw(_("{0} holds {1}; cannot settle {2}").format(doc.name, balance, amount))
	return amount


def _cash_account(company: str, account=None, mode_of_payment=None) -> str:
	if not account and mode_of_payment:
		account = frappe.db.get_value(
			"Mode of Payment Account", {"parent": mode_of_payment, "company": company}, "default_account"
		)
	account = account or frappe.get_cached_value("Company", company, "default_cash_account")
	if not account:
		frappe.throw(_("Choose the cash or bank account"))
	return account


def _journal(doc, rows, action: str, reference=None) -> str:
	je = frappe.new_doc("Journal Entry")
	je.update(
		{
			"voucher_type": "Journal Entry",
			"company": doc.company,
			"posting_date": nowdate(),
			"rental_deposit": doc.name,
			"user_remark": _("Rental deposit {0}: {1} for booking {2}").format(
				doc.name, _(action), doc.rental_booking
			),
		}
	)
	if reference:
		je.cheque_no, je.cheque_date = reference, nowdate()
	cost_center = frappe.db.get_value("Rental Booking", doc.rental_booking, "cost_center")
	for account, debit, credit, extra in rows:
		row = {
			"account": account,
			"debit_in_account_currency": debit,
			"credit_in_account_currency": credit,
			**(extra or {}),
		}
		if cost_center:
			row["cost_center"] = cost_center
		je.append("accounts", row)
	je.flags.ignore_permissions = True  # the caller's permission on the deposit was checked by the API
	je.insert()
	je.submit()
	return je.name


def _finish(doc, action: str, amount: float, je: str) -> None:
	doc.append(
		"entries", {"action": action, "amount": amount, "journal_entry": je, "posting_date": nowdate()}
	)
	doc.balance_held = held(doc)
	received = flt(doc.amount_received)
	if received <= 0:
		doc.status = "Requested"
	elif doc.balance_held <= 0 and (doc.amount_applied or doc.amount_refunded or doc.amount_forfeited):
		doc.status = "Settled"
	elif received < flt(doc.amount_required):
		doc.status = "Partly Received"
	else:
		doc.status = "Held"
	doc.flags.ignore_permissions = True
	doc.save()
	grand_total = frappe.db.get_value("Rental Booking", doc.rental_booking, "grand_total")
	frappe.db.set_value(
		"Rental Booking",
		doc.rental_booking,
		{"deposit_paid": received, "balance": flt(flt(grand_total) - received, _precision())},
		update_modified=False,
	)

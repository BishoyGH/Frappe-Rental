"""Customer booking flow (T35): select, dates, extras, details, sign, pay.

Customers have no desk permissions on Rental Booking. Every call here is scoped instead: a booking is
only reachable by a user who acts for its customer (``my_customers``), and writes on the booking and its
contract run as Administrator (``_as_system``) after that check, because ERPNext controllers check the
session user's permissions deep inside (item details, price lists).

Guest checkout: a guest who gives an email no account uses gets a Website User, a Customer and a Contact
linking the two, and is signed in for the rest of the flow. An email that already has an account must sign
in first, so nobody can book (or read bookings) as someone else by typing their address.

Extras are the optional charges on the item's rate card. A chosen extra becomes a manual charge row priced
like a mandatory one.

Sign: a Rental Type with ``requires_contract`` gets a Rental Contract from the type's terms template. The
customer signs it in the flow (typed name), which activates it; no countersignature is needed for a
self-service booking.

Pay: ``payment`` (T36) returns where to pay the deposit. ``finish`` confirms once the guards pass.
"""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_datetime, getdate, validate_email_address

from frappe_rental.services import booking as booking_service
from frappe_rental.services import contracts, esign, lifecycle, pricing, public_site, setup_ui
from frappe_rental.services import terms as terms_service


@contextmanager
def _as_system():
	"""Run ERPNext side effects (Sales Order, Contract, deposit request) as Administrator.

	Only used after ``own_booking``/``ensure_customer`` scoped the call to the session user's own customer.
	ERPNext checks the session user's permissions deep inside its controllers (item details, price
	lists), which a portal customer never has. The session user is restored afterwards.
	"""
	user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(user)


class SignInRequired(frappe.PermissionError):
	http_status_code = 403


def my_customers(user: str | None = None) -> list[str]:
	"""Customers the user may act for: Customer portal users, then contacts linked to a customer."""
	user = user or frappe.session.user
	if user == "Guest":
		return []
	names = set(
		frappe.get_all("Portal User", filters={"parenttype": "Customer", "user": user}, pluck="parent")
	)
	contacts = frappe.get_all("Contact", filters={"user": user}, pluck="name")
	if contacts:
		names |= set(
			frappe.get_all(
				"Dynamic Link",
				filters={"parenttype": "Contact", "parent": ["in", contacts], "link_doctype": "Customer"},
				pluck="link_name",
			)
		)
	return sorted(names)


def own_booking(name: str):
	"""The booking, if the session user acts for its customer. Otherwise a not-found error (no leak)."""
	if not name or not frappe.db.exists("Rental Booking", name):
		frappe.throw(_("Booking not found"), frappe.DoesNotExistError)
	doc = frappe.get_doc("Rental Booking", name)
	if doc.customer not in my_customers():
		frappe.throw(_("Booking not found"), frappe.DoesNotExistError)
	return doc


def extras(item: str) -> list[dict]:
	"""Optional charges a customer may add to a booking of this published item."""
	row = public_site._published(item)
	if not row.rate_card:
		return []
	card = frappe.get_cached_doc("Rental Rate Card", row.rate_card)
	out = []
	for c in card.charges:
		if c.is_mandatory:
			continue
		charge = frappe.get_cached_doc("Rental Charge", c.charge)
		out.append(
			{
				"charge": charge.name,
				"label": charge.charge_name or charge.name,
				"charge_type": charge.charge_type,
				"amount": charge.amount,
				"percent": charge.percent,
				"applies_per": charge.applies_per,
			}
		)
	return out


def _ensure_contact(customer: str, user: str, full_name: str, email: str, phone: str | None) -> None:
	if frappe.db.exists("Contact", {"user": user}):
		contact = frappe.get_doc("Contact", {"user": user})
		if not any(link.link_doctype == "Customer" and link.link_name == customer for link in contact.links):
			contact.append("links", {"link_doctype": "Customer", "link_name": customer})
			contact.flags.ignore_permissions = True  # the user's own contact
			contact.save()
		return
	first, _sep, last = full_name.partition(" ")
	contact = frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": first,
			"last_name": last,
			"user": user,
			"email_ids": [{"email_id": email, "is_primary": 1}],
			"phone_nos": [{"phone": phone, "is_primary_mobile_no": 1}] if phone else [],
			"links": [{"link_doctype": "Customer", "link_name": customer}],
		}
	)
	contact.flags.ignore_permissions = True  # created for the signing-up customer, scoped to them
	contact.insert()


def _new_customer(full_name: str, user: str, email: str, phone: str | None) -> str:
	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": full_name,
			"customer_type": "Individual",
			"customer_group": setup_ui._first_leaf("Customer Group"),
			"territory": setup_ui._first_leaf("Territory"),
			"email_id": email,
			"mobile_no": phone or None,
		}
	)
	customer.flags.ignore_permissions = True  # self sign-up: the customer record of the new user only
	customer.insert()
	_ensure_contact(customer.name, user, full_name, email, phone)
	return customer.name


def ensure_customer(details: dict) -> dict:
	"""The customer the booking is for. Creates User, Customer and Contact for a new guest."""
	details = details or {}
	full_name = (details.get("full_name") or "").strip()
	email = (details.get("email") or "").strip().lower()
	phone = (details.get("phone") or "").strip() or None
	user = frappe.session.user
	if user != "Guest":
		existing = my_customers(user)
		if existing:
			return {"customer": existing[0], "user": user, "new_user": False}
		name = full_name or frappe.utils.get_fullname(user)
		email = frappe.db.get_value("User", user, "email") or email
		return {"customer": _new_customer(name, user, email, phone), "user": user, "new_user": False}
	if not full_name:
		frappe.throw(_("Your name is required"))
	if not email or not validate_email_address(email):
		frappe.throw(_("A valid email is required"))
	if frappe.db.exists("User", {"email": email}) or frappe.db.exists("User", email):
		frappe.throw(_("An account with this email exists. Sign in to continue."), SignInRequired)
	first, _sep, last = full_name.partition(" ")
	new_user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": first,
			"last_name": last,
			"user_type": "Website User",
			"send_welcome_email": 0,
			"mobile_no": phone,
		}
	)
	if frappe.db.exists("Role", "Customer"):
		new_user.append("roles", {"role": "Customer"})
	new_user.flags.ignore_permissions = True  # guest checkout creates the guest's own account
	new_user.insert()
	customer = _new_customer(full_name, new_user.name, email, phone)
	login_manager = getattr(frappe.local, "login_manager", None)
	if login_manager and getattr(frappe.local, "request", None) is not None:
		login_manager.login_as(new_user.name)
	else:
		frappe.set_user(new_user.name)
	return {"customer": customer, "user": new_user.name, "new_user": True}


def _extra_rows(item_row, chosen: list[str], doc) -> list[dict]:
	offered = {e["charge"]: e for e in extras(item_row.name)}
	unknown = [c for c in chosen if c not in offered]
	if unknown:
		frappe.throw(_("{0} is not offered for this item").format(", ".join(unknown)))
	line = doc.lines[0]
	precision = booking_service._precision(doc)
	rows = []
	for name in chosen:
		e = offered[name]
		amount = pricing._charges(
			[{**e, "is_mandatory": 1, "charge_name": e["label"]}],
			flt(line.amount),
			flt(line.units),
			flt(line.qty),
			precision,
		)[0]["amount"]
		rows.append({"charge": name, "description": e["label"], "amount": amount, "is_manual": 1})
	return rows


def _contract_for(doc) -> None:
	rtype = frappe.get_cached_doc("Rental Type", doc.rental_type)
	if not rtype.requires_contract:
		return
	template = terms_service.template_for(doc.rental_type, frappe.local.lang)
	if not template:
		frappe.throw(_("{0} cannot be booked online yet: it has no terms template").format(doc.rental_type))
	contract = frappe.get_doc(
		{
			"doctype": "Rental Contract",
			"customer": doc.customer,
			"company": doc.company,
			"start_date": getdate(doc.from_datetime),
			"end_date": getdate(doc.to_datetime),
			"terms_template": template,
		}
	)
	contract.insert()  # runs inside _as_system: the caller checked the booking is the customer's
	contracts.send_for_signature(contract)
	contract.save()
	doc.db_set("rental_contract", contract.name)


def start(data: dict) -> dict:
	"""Create and hold the booking for the chosen item, dates, quantity and extras."""
	item = public_site._published(data.get("item"))
	start_at, end_at = get_datetime(data.get("from_datetime")), get_datetime(data.get("to_datetime"))
	if not start_at or not end_at:
		frappe.throw(_("Choose your dates"))
	if start_at < get_datetime(add_days(frappe.utils.now_datetime(), -1)):
		frappe.throw(_("Choose dates in the future"))
	who = ensure_customer(data.get("details") or {})
	doc = frappe.get_doc(
		{
			"doctype": "Rental Booking",
			"customer": who["customer"],
			"rental_type": item.rental_type,
			"location": item.location,
			"from_datetime": start_at,
			"to_datetime": end_at,
			"source": "Portal",
			"coupon_code": data.get("coupon_code") or None,
			"lines": [{"rental_item": item.name, "qty": flt(data.get("qty")) or 1}],
		}
	)
	booking_service.validate_booking(doc)
	booking_service.apply_pricing(doc)
	for row in _extra_rows(item, list(data.get("extras") or []), doc):
		doc.append("charges", row)
	with _as_system():  # the customer's own booking: customer set from the session above
		doc.insert()
		lifecycle.place_hold(doc)
		_contract_for(doc)
	return {**summary(doc.name), "new_user": who["new_user"], "csrf_token": _csrf()}


def _csrf() -> str | None:
	try:
		return frappe.sessions.get_csrf_token()
	except Exception:
		return None


def summary(name: str) -> dict:
	doc = own_booking(name)
	rtype = frappe.get_cached_doc("Rental Type", doc.rental_type)
	contract = None
	if doc.rental_contract:
		c = frappe.db.get_value(
			"Rental Contract",
			doc.rental_contract,
			["name", "status", "rendered_terms", "signed_on", "require_otp"],
			as_dict=True,
		)
		contract = {
			"name": c.name,
			"status": c.status,
			"html": c.rendered_terms,
			"signed": bool(c.signed_on),
			"require_otp": c.require_otp,
		}
	return {
		"name": doc.name,
		"status": doc.status,
		"docstatus": doc.docstatus,
		"hold_expires_on": doc.hold_expires_on,
		"from_datetime": doc.from_datetime,
		"to_datetime": doc.to_datetime,
		"currency": doc.currency,
		"lines": [
			{
				"rental_item": ln.rental_item,
				"item_name": frappe.db.get_value("Rental Item", ln.rental_item, "item_name"),
				"qty": ln.qty,
				"amount": ln.amount,
			}
			for ln in doc.lines
		],
		"charges": [{"description": c.description, "amount": c.amount} for c in doc.charges],
		"net_total": doc.net_total,
		"total_taxes": doc.total_taxes,
		"grand_total": doc.grand_total,
		"deposit_required": doc.deposit_required if rtype.requires_deposit else 0,
		"deposit_paid": doc.deposit_paid,
		"contract": contract,
		"needs_signature": bool(contract and not contract["signed"]),
		"needs_deposit": bool(rtype.requires_deposit and flt(doc.deposit_paid) < flt(doc.deposit_required)),
	}


def sign(name: str, signer_name: str, signature: str, otp: str | None = None) -> dict:
	doc = own_booking(name)
	if not doc.rental_contract:
		frappe.throw(_("This booking has nothing to sign"))
	contract = frappe.get_doc("Rental Contract", doc.rental_contract)
	esign.customer_sign(contract, signer_name, signature, "Typed", otp)
	contract.reload()
	with _as_system():  # signer checked by esign.can_sign_for above
		erpnext_contract = contracts.activate(contract, contract.signed_by)
		contract.save()
	doc.db_set("contract", erpnext_contract)
	return summary(name)


def finish(name: str) -> dict:
	"""Confirm the held booking. The lifecycle guards (hold, deposit, contract) still apply."""
	doc = own_booking(name)
	if doc.docstatus == 1:
		return summary(name)
	if doc.status != "Hold":
		frappe.throw(_("This booking can no longer be confirmed"))
	with _as_system():  # the customer's own held booking (own_booking above)
		doc.submit()
	return summary(name)


def payment(name: str) -> dict:
	"""Online deposit payment: filled by the payment adapters (T36)."""
	own_booking(name)
	frappe.throw(_("Online payment is not set up. Contact us to pay the deposit."))

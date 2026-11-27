"""My bookings portal endpoints (T37). Signed-in customers only; ownership is checked in ``services.portal``."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from frappe_rental.services import contract_views, portal


def _signed_in() -> None:
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to see your bookings"), frappe.PermissionError)


@frappe.whitelist(methods=["GET", "POST"])
def listing(start: int = 0, page_length: int = 20) -> dict:
	_signed_in()
	return portal.listing(start, page_length)


@frappe.whitelist(methods=["GET", "POST"])
def detail(name: str) -> dict:
	_signed_in()
	return portal.detail(name)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=60)
def change(name: str, from_datetime: str, to_datetime: str) -> dict:
	_signed_in()
	return portal.change(name, from_datetime, to_datetime)


@frappe.whitelist(methods=["GET", "POST"])
def cancel_preview(name: str) -> dict:
	_signed_in()
	return portal.cancel_preview(name)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=60)
def cancel(name: str) -> dict:
	_signed_in()
	return portal.cancel(name)


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=30, seconds=60)
def download(name: str, kind: str, ref: str) -> None:
	_signed_in()
	portal.download(name, kind, ref)


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=30, seconds=60)
def download_contract(name: str) -> None:
	_signed_in()
	contract_views.download(name)

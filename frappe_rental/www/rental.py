"""Staff app entry (T17): serves the Vue SPA at /rental for signed-in users with a rental role."""

import csv
import os
import re

import frappe
from frappe import _

from frappe_rental.services.permissions import MATRIX

no_cache = 1
STAFF_ROLES = frozenset({role for roles in MATRIX.values() for role in roles} | {"System Manager"})


def has_app_access(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user == "Guest":
		return False
	return bool(STAFF_ROLES.intersection(frappe.get_roles(user)))


# Customer pages of the same SPA (T35, T37): open to guests and to users without a rental role.
PORTAL_PATHS = ("/rental/book", "/rental/my-bookings", "/rental/my-contracts")


def is_portal_path(path: str | None) -> bool:
	path = (path or "").rstrip("/")
	return any(path == p or path.startswith(p + "/") for p in PORTAL_PATHS)


RTL_LANGUAGES = frozenset({"ar", "he", "fa", "ur"})


def messages(lang: str | None = None) -> dict:
	"""SPA strings for the session language, from the app's translations/<lang>.csv (exact code, then base)."""
	lang = (lang or frappe.local.lang or "en").replace("_", "-")
	if not re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})?", lang):
		return {}
	for code in dict.fromkeys((lang, lang.split("-")[0])):
		path = frappe.get_app_path("frappe_rental", "translations", f"{code}.csv")
		if os.path.exists(path):
			with open(path, newline="", encoding="utf-8") as f:
				return {row[0]: row[1] for row in csv.reader(f) if len(row) >= 2 and row[1].strip()}
	return {}


def direction(lang: str | None = None) -> str:
	return (
		"rtl" if (lang or frappe.local.lang or "en").split("-")[0].split("_")[0] in RTL_LANGUAGES else "ltr"
	)


def page_language(context) -> None:
	context.lang = (frappe.local.lang or "en").replace("_", "-")
	context.dir = direction()


def get_context(context):
	page_language(context)
	path = frappe.request.path if frappe.request else ""
	if is_portal_path(path):
		context.boot = {
			"csrf_token": frappe.sessions.get_csrf_token(),
			"site_name": frappe.local.site,
			"rental_boot": portal_boot(),
		}
		return context
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.utils.quote(
			frappe.request.path if frappe.request else "/rental"
		)
		raise frappe.Redirect
	if not has_app_access():
		frappe.throw(_("You need a Rental role to open the rental app."), frappe.PermissionError)
	context.boot = {
		"csrf_token": frappe.sessions.get_csrf_token(),
		"site_name": frappe.local.site,
		"rental_boot": boot_data(),
	}
	return context


def boot_data() -> dict:
	user = frappe.session.user
	company = frappe.db.get_single_value(
		"Rental Settings", "default_company"
	) or frappe.defaults.get_user_default("Company")
	return {
		"user": user,
		"full_name": frappe.utils.get_fullname(user),
		"company": company or "",
		"roles": sorted(STAFF_ROLES.intersection(frappe.get_roles(user))),
		"messages": messages(),
	}


def portal_boot() -> dict:
	user = frappe.session.user
	return {
		"user": user,
		"full_name": "" if user == "Guest" else frappe.utils.get_fullname(user),
		"portal": True,
		"is_staff": has_app_access(user),
		"messages": messages(),
	}

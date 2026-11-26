"""Staff app entry (T17): serves the Vue SPA at /rental for signed-in users with a rental role."""

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


def get_context(context):
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
	}

"""Public catalogue (T34): /rentals, server-rendered with filters from the query string."""

import frappe
from frappe import _

from frappe_rental.services import public_site

no_cache = 1


def get_context(context):
	args = frappe.form_dict
	context.title = _("Rentals")
	context.filters = {k: args.get(k) or "" for k in ("rental_type", "location", "from", "to", "guests")}
	context.options = public_site.filter_options()
	error = None
	try:
		result = public_site.list_items(
			rental_type=args.get("rental_type") or None,
			location=args.get("location") or None,
			from_datetime=args.get("from") or None,
			to_datetime=args.get("to") or None,
			guests=args.get("guests") or None,
			start=args.get("start") or 0,
		)
	except frappe.ValidationError as e:
		result = {"items": [], "total": 0, "start": 0, "page_length": public_site.PAGE}
		error = str(e)
	context.result = result
	context.error = error
	context.metatags = {
		"title": _("Rentals"),
		"description": _("Browse what you can rent and check the price."),
	}
	return context

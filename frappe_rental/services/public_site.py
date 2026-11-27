"""Public website data (T34): published items only, no customer data.

Everything here is safe for Guest: it reads published Rental Items, their prices and day-level availability
counts. Callers in ``api.public`` add rate limits.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime

from frappe_rental.services import search as search_service

PAGE = 24


def _published(name: str) -> frappe._dict:
	if not isinstance(name, str) or not name or len(name) > 140:
		frappe.throw(_("This item is not available"), frappe.DoesNotExistError)
	row = frappe.db.get_value(
		"Rental Item",
		{"name": name, "is_published": 1},
		["name", "item_name", "rental_type", "location", "rate_card", "route", "image", "capacity_people"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("This item is not available"), frappe.DoesNotExistError)
	return row


def list_items(
	rental_type=None, location=None, qty=1, from_datetime=None, to_datetime=None, start=0, guests=None
) -> dict:
	"""Published items, filtered. With dates, only items with a free unit, and their price for the period."""
	filters = {"is_published": 1}
	if rental_type:
		filters["rental_type"] = rental_type
	if location:
		filters["location"] = location
	if cint(guests):
		filters["capacity_people"] = [">=", cint(guests)]
	items = frappe.get_all(
		"Rental Item",
		filters=filters,
		fields=["name", "item_name", "rental_type", "location", "route", "image", "capacity_people"],
		order_by="item_name asc",
	)
	prices = {}
	if from_datetime and to_datetime and items:
		from frappe_rental.services import booking as booking_service

		names = {i.name for i in items}
		free = search_service.search(
			booking_service.moment(from_datetime, _("From")),
			booking_service.moment(to_datetime, _("To")),
			rental_type=rental_type,
			qty=flt(qty) or 1,
			location=location,
		)
		for row in free:
			if row["rental_item"] in names and row["rental_item"] not in prices:
				prices[row["rental_item"]] = {"price": row.get("price"), "currency": row.get("currency")}
		items = [i for i in items if i.name in prices]
	start = max(cint(start), 0)
	page = items[start : start + PAGE]
	for i in page:
		i.update(prices.get(i.name, {}))
	return {"items": page, "total": len(items), "start": start, "page_length": PAGE}


def filter_options() -> dict:
	types = frappe.get_all("Rental Item", filters={"is_published": 1}, pluck="rental_type", distinct=True)
	locations = frappe.get_all("Rental Item", filters={"is_published": 1}, pluck="location", distinct=True)
	return {
		"rental_types": sorted(t for t in types if t),
		"locations": sorted(loc for loc in locations if loc),
	}


def quote(item: str, from_datetime, to_datetime, qty=1) -> dict:
	from frappe_rental.services import booking as booking_service

	row = _published(item)
	doc = frappe.get_doc(
		{
			"doctype": "Rental Booking",
			"rental_type": row.rental_type,
			"location": row.location,
			"from_datetime": from_datetime,
			"to_datetime": to_datetime,
			"lines": [{"rental_item": row.name, "qty": flt(qty) or 1}],
		}
	)
	booking_service.validate_booking(doc)
	booking_service.apply_pricing(doc)
	free = search_service.search(
		get_datetime(from_datetime),
		get_datetime(to_datetime),
		rental_item=row.name,
		qty=flt(qty) or 1,
		with_price=False,
	)
	return {
		"item": row.name,
		"item_name": row.item_name,
		"available": bool(free),
		"currency": doc.currency,
		"net_total": doc.net_total,
		"total_taxes": doc.total_taxes,
		"grand_total": doc.grand_total,
		"deposit_required": doc.deposit_required,
		"lines": [
			{"time_unit": ln.time_unit, "units": ln.units, "rate": ln.rate, "amount": ln.amount}
			for ln in doc.lines
		],
	}


def calendar(item: str, year: int, month: int) -> dict:
	"""Per day: 'free', 'partial' or 'busy' for the item as a whole (counts are not shown to guests)."""
	_published(item)
	days = search_service.calendar(year, month, rental_item=item)
	out = {}
	for day, c in days.items():
		out[day] = "free" if c.get("free") else ("partial" if c.get("partial") else "busy")
	return out


def item_context(doc) -> dict:
	"""Extra context for the item page: gallery, SEO tags and the 'from' price."""
	gallery = [i.image for i in doc.images or [] if i.image] or ([doc.image] if doc.image else [])
	card = frappe.get_cached_doc("Rental Rate Card", doc.rate_card) if doc.rate_card else None
	rates = sorted((r for r in (card.rates if card else []) if not r.rental_unit), key=lambda r: flt(r.rate))
	from_rate = rates[0] if rates else None
	description = frappe.utils.strip_html(doc.description or "")[:160]
	return {
		"gallery": gallery,
		"from_rate": {"rate": from_rate.rate, "time_unit": from_rate.time_unit, "currency": card.currency}
		if from_rate
		else None,
		"metatags": {
			"title": doc.item_name,
			"description": description or doc.item_name,
			"image": gallery[0] if gallery else None,
			"og:type": "product",
		},
	}

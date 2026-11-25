"""Rental Booking (T12): validation against the Rental Type and pricing through `services.pricing`.

The booking loads rate cards and context from the database into plain dicts, then calls the pure
`pricing.quote` once per line. Booking-level tax and deposit are computed here from the totals.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime

from frappe_rental.services import pricing

# Rental Type time units that pricing knows under another name.
TYPE_UNIT_TO_PRICING = {"Night": "Day"}


def validate_booking(doc) -> None:
	if get_datetime(doc.to_datetime) <= get_datetime(doc.from_datetime):
		frappe.throw(_("To must be after From"))
	rtype = frappe.get_cached_doc("Rental Type", doc.rental_type)
	_set_defaults(doc, rtype)
	for line in doc.lines:
		_validate_line(doc, line, rtype)
	_validate_duration(doc, rtype)


def _set_defaults(doc, rtype) -> None:
	settings = frappe.get_cached_doc("Rental Settings")
	if doc.location and not doc.company:
		doc.company = frappe.db.get_value("Rental Location", doc.location, "company")
	doc.company = doc.company or settings.default_company
	if doc.location and not doc.cost_center:
		doc.cost_center = frappe.db.get_value("Rental Location", doc.location, "cost_center")
	if not doc.currency and doc.company:
		doc.currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	doc.price_list = doc.price_list or settings.default_price_list
	if not doc.taxes_and_charges and rtype.tax_template:
		doc.taxes_and_charges = rtype.tax_template


def _validate_line(doc, line, rtype) -> None:
	item_type = frappe.db.get_value("Rental Item", line.rental_item, "rental_type")
	if item_type != doc.rental_type:
		frappe.throw(
			_("Row {0}: {1} is a {2}, not a {3}").format(
				line.idx, line.rental_item, item_type, doc.rental_type
			)
		)
	if line.rental_unit:
		unit_item = frappe.db.get_value("Rental Unit", line.rental_unit, "rental_item")
		if unit_item != line.rental_item:
			frappe.throw(_("Row {0}: unit {1} belongs to {2}").format(line.idx, line.rental_unit, unit_item))
	line.qty = flt(line.qty) or 1
	if line.qty <= 0:
		frappe.throw(_("Row {0}: quantity must be positive").format(line.idx))
	if line.qty != 1 and not (rtype.allow_quantity or rtype.identification_mode == "Pooled"):
		frappe.throw(_("Row {0}: {1} does not allow quantities above 1").format(line.idx, doc.rental_type))
	start, end = _line_range(doc, line)
	if end <= start:
		frappe.throw(_("Row {0}: To must be after From").format(line.idx))
	if get_datetime(start) < get_datetime(doc.from_datetime) or get_datetime(end) > get_datetime(
		doc.to_datetime
	):
		frappe.throw(_("Row {0}: dates must fall inside the booking period").format(line.idx))


def _validate_duration(doc, rtype) -> None:
	if not (flt(rtype.min_duration) or flt(rtype.max_duration)):
		return
	unit = TYPE_UNIT_TO_PRICING.get(rtype.time_unit, rtype.time_unit)
	start, end = pricing.local_range({"from_datetime": doc.from_datetime, "to_datetime": doc.to_datetime})
	duration = pricing.billable_units(unit, start, end, {}, "Pro-rata")
	if flt(rtype.min_duration) and duration < flt(rtype.min_duration):
		frappe.throw(
			_("Minimum duration for {0} is {1} {2}").format(
				doc.rental_type, rtype.min_duration, rtype.time_unit
			)
		)
	if flt(rtype.max_duration) and duration > flt(rtype.max_duration):
		frappe.throw(
			_("Maximum duration for {0} is {1} {2}").format(
				doc.rental_type, rtype.max_duration, rtype.time_unit
			)
		)


def apply_pricing(doc) -> None:
	"""Price every line, rebuild automatic charges, then taxes, totals and deposit. Safe to rerun."""
	precision = _precision(doc)
	customer_group = frappe.db.get_value("Customer", doc.customer, "customer_group")
	timezone = doc.location and frappe.db.get_value("Rental Location", doc.location, "timezone")
	coupon_pct = coupon_discount_pct(doc.coupon_code)
	manual = [c for c in doc.charges or [] if c.is_manual]
	auto = []
	for line in doc.lines:
		card = load_rate_card(_rate_card_for(line))
		start, end = _line_range(doc, line)
		request = {
			"from_datetime": start,
			"to_datetime": end,
			"timezone": timezone,
			"qty": line.qty,
			"rental_unit": line.rental_unit,
			"customer_group": customer_group,
			"seasons": card["seasons"],
			"group_discount_pct": line.discount_pct,
			"coupon_discount_pct": coupon_pct,
			"precision": precision,
		}
		try:
			result = pricing.quote_with_hooks(request, card)
		except pricing.PricingError as e:
			frappe.throw(_("Row {0}: {1}").format(line.idx, _(str(e))))
		line.time_unit = result["time_unit"]
		line.units = result["units"]
		line.rate = result["rate"]
		line.discount_amount = result["discount_amount"]
		line.amount = flt(result["base_amount"] - result["discount_amount"], precision)
		line.applied_rule = result["applied_rule"]
		auto += [
			{"charge": c["charge"], "description": c["charge"], "amount": c["amount"]}
			for c in result["charges"]
		]
	doc.set("charges", [])
	for row in auto:
		doc.append("charges", {**row, "is_manual": 0})
	for row in manual:
		doc.append(
			"charges",
			{"charge": row.charge, "description": row.description, "amount": row.amount, "is_manual": 1},
		)
	doc.net_total = flt(
		sum(flt(line.amount) for line in doc.lines) + sum(flt(c.amount) for c in doc.charges), precision
	)
	doc.total_taxes = flt(doc.net_total * tax_rate(doc.taxes_and_charges) / 100, precision)
	doc.grand_total = flt(doc.net_total + doc.total_taxes, precision)
	doc.deposit_required = deposit_amount(doc.rental_type, doc.grand_total, precision)
	doc.balance = flt(doc.grand_total - flt(doc.deposit_paid), precision)


def load_rate_card(name: str) -> dict:
	card = frappe.get_cached_doc("Rental Rate Card", name)
	if not card.enabled:
		frappe.throw(_("Rate card {0} is disabled").format(name))
	rates = [r.as_dict() for r in card.rates]
	charges = []
	for row in card.charges:
		charge = frappe.get_cached_doc("Rental Charge", row.charge).as_dict()
		charge["is_mandatory"] = row.is_mandatory
		charges.append(charge)
	season_names = {r["season"] for r in rates if r.get("season")}
	seasons = (
		{
			s.name: (s.from_date, s.to_date)
			for s in frappe.get_all(
				"Rental Season",
				filters={"name": ["in", list(season_names)]},
				fields=["name", "from_date", "to_date"],
			)
		}
		if season_names
		else {}
	)
	return {
		"currency": card.currency,
		"rounding_mode": card.rounding_mode,
		"minimum_charge": card.minimum_charge,
		"rates": rates,
		"charges": charges,
		"seasons": seasons,
	}


def coupon_discount_pct(coupon_code: str | None) -> float:
	"""Percent discount from an ERPNext Coupon Code's Pricing Rule; 0 when none applies."""
	if not coupon_code:
		return 0.0
	rule = frappe.db.get_value("Coupon Code", coupon_code, "pricing_rule")
	if not rule:
		return 0.0
	values = frappe.db.get_value(
		"Pricing Rule", rule, ["rate_or_discount", "discount_percentage", "disable"], as_dict=True
	)
	if not values or values.disable or values.rate_or_discount != "Discount Percentage":
		return 0.0
	return flt(values.discount_percentage)


def tax_rate(template: str | None) -> float:
	"""Sum of "On Net Total" rates in a Sales Taxes and Charges Template."""
	if not template:
		return 0.0
	rows = frappe.get_all(
		"Sales Taxes and Charges",
		filters={
			"parent": template,
			"parenttype": "Sales Taxes and Charges Template",
			"charge_type": "On Net Total",
		},
		pluck="rate",
	)
	return flt(sum(flt(r) for r in rows))


def deposit_amount(rental_type: str, grand_total: float, precision: int) -> float:
	rule_name = frappe.db.get_value("Rental Type", rental_type, "deposit_rule")
	if not rule_name:
		return 0.0
	rule = frappe.get_cached_doc("Rental Deposit Rule", rule_name)
	if rule.deposit_type == "Fixed":
		return flt(rule.amount, precision)
	return flt(flt(grand_total) * flt(rule.percent) / 100, precision)


def _rate_card_for(line) -> str:
	card = frappe.db.get_value("Rental Item", line.rental_item, "rate_card")
	if not card:
		frappe.throw(_("Row {0}: {1} has no rate card").format(line.idx, line.rental_item))
	return card


def _line_range(doc, line):
	return line.from_datetime or doc.from_datetime, line.to_datetime or doc.to_datetime


def _precision(doc) -> int:
	from frappe.utils import cint

	return (
		cint(frappe.get_meta("Rental Booking").get_field("grand_total").precision)
		or cint(frappe.db.get_default("currency_precision"))
		or 2
	)

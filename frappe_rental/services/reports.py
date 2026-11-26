"""Rental reports and dashboard figures (T30). Read-only queries; every report module calls these.

- revenue: invoiced net revenue (base currency) by rental type and location, from submitted Sales
  Invoices linked to bookings, credit notes included. It reconciles to the GL: the same invoices'
  income-account entries add up to the same total (tested).
- occupancy / utilisation: booked hours of each unit in a period over the hours in the period,
  from confirmed bookings (Confirmed, Checked Out, Returned, Closed).
- overdue returns: bookings still Checked Out after their end.
- unit history: bookings, handovers, damage reports and blocks of one unit, newest first.
- asset ROI: revenue per unit against the linked asset's purchase amount.
- availability: free units in a window, through the T15 search service.
"""

import frappe
from frappe.utils import flt, get_datetime, now_datetime

LIVE = ("Confirmed", "Checked Out", "Returned", "Closed")


def revenue(from_date, to_date, company=None, group_by="rental_type") -> list[dict]:
	if group_by not in ("rental_type", "location"):
		frappe.throw("group_by must be rental_type or location")
	conditions, values = _invoice_conditions(from_date, to_date, company)
	return frappe.db.sql(
		f"""select coalesce(b.{group_by}, '') as `group`, sum(i.base_net_amount) as revenue,
			count(distinct si.name) as invoices
		from `tabSales Invoice Item` i
		join `tabSales Invoice` si on si.name = i.parent
		join `tabRental Booking` b on b.name = si.rental_booking
		where {conditions}
		group by b.{group_by} order by revenue desc""",
		values,
		as_dict=True,
	)


def revenue_gl_total(from_date, to_date, company=None) -> float:
	"""The same invoices' income entries in the GL (credit minus debit), for reconciliation."""
	conditions, values = _invoice_conditions(from_date, to_date, company)
	row = frappe.db.sql(
		f"""select sum(g.credit - g.debit) from `tabGL Entry` g
		join `tabAccount` a on a.name = g.account and a.root_type = 'Income'
		where g.is_cancelled = 0 and g.voucher_type = 'Sales Invoice' and g.voucher_no in (
			select si.name from `tabSales Invoice` si
			join `tabRental Booking` b on b.name = si.rental_booking
			where {conditions})""",
		values,
	)
	return flt(row[0][0]) if row else 0.0


def _invoice_conditions(from_date, to_date, company):
	conditions = "si.docstatus = 1 and si.posting_date between %(from_date)s and %(to_date)s"
	values = {"from_date": from_date, "to_date": to_date}
	if company:
		conditions += " and si.company = %(company)s"
		values["company"] = company
	return conditions, values


def occupancy(from_datetime, to_datetime, location=None, rental_type=None) -> list[dict]:
	start, end = get_datetime(from_datetime), get_datetime(to_datetime)
	period_hours = (end - start).total_seconds() / 3600
	if period_hours <= 0:
		frappe.throw("The period must end after it starts")
	filters = {"status": ["!=", "Retired"], "is_group": 0}
	if location:
		filters["location"] = location
	if rental_type:
		filters["rental_type"] = rental_type
	units = frappe.get_all(
		"Rental Unit", filters=filters, fields=["name", "rental_item", "rental_type", "location"]
	)
	booked = {u.name: 0.0 for u in units}
	if units:
		rows = frappe.db.sql(
			"""select l.rental_unit, coalesce(l.from_datetime, b.from_datetime) as f,
				coalesce(l.to_datetime, b.to_datetime) as t
			from `tabRental Booking Line` l join `tabRental Booking` b on b.name = l.parent
			where b.docstatus = 1 and b.status in %(live)s and l.rental_unit in %(units)s
			and coalesce(l.from_datetime, b.from_datetime) < %(end)s
			and coalesce(l.to_datetime, b.to_datetime) > %(start)s""",
			{"live": LIVE, "units": tuple(booked), "start": start, "end": end},
			as_dict=True,
		)
		for r in rows:
			overlap = (min(get_datetime(r.t), end) - max(get_datetime(r.f), start)).total_seconds() / 3600
			booked[r.rental_unit] = min(booked[r.rental_unit] + max(overlap, 0), period_hours)
	return [
		{
			**u,
			"booked_hours": flt(booked[u.name], 2),
			"period_hours": flt(period_hours, 2),
			"occupancy_pct": flt(booked[u.name] / period_hours * 100, 2),
		}
		for u in units
	]


def overdue_returns(now=None) -> list[dict]:
	now = get_datetime(now or now_datetime())
	rows = frappe.get_all(
		"Rental Booking",
		filters={"docstatus": 1, "status": "Checked Out", "to_datetime": ["<", now]},
		fields=["name", "customer", "rental_type", "location", "to_datetime"],
		order_by="to_datetime asc",
	)
	for r in rows:
		r["hours_overdue"] = flt((now - get_datetime(r.to_datetime)).total_seconds() / 3600, 1)
	return rows


def unit_history(unit: str) -> list[dict]:
	events = []
	for r in frappe.db.sql(
		"""select b.name, b.customer, b.status, coalesce(l.from_datetime, b.from_datetime) as at
		from `tabRental Booking Line` l join `tabRental Booking` b on b.name = l.parent
		where l.rental_unit = %s and b.docstatus < 2""",
		unit,
		as_dict=True,
	):
		events.append(
			{"at": r.at, "kind": "Booking", "reference": r.name, "detail": f"{r.customer} ({r.status})"}
		)
	for r in frappe.db.sql(
		"""select h.name, h.handover_type, h.posted_on, h.customer from `tabRental Handover Line` l
		join `tabRental Handover` h on h.name = l.parent where l.rental_unit = %s and h.docstatus = 1""",
		unit,
		as_dict=True,
	):
		events.append({"at": r.posted_on, "kind": r.handover_type, "reference": r.name, "detail": r.customer})
	for r in frappe.get_all(
		"Rental Damage Report",
		filters={"rental_unit": unit},
		fields=["name", "reported_on", "status", "description"],
	):
		events.append(
			{
				"at": get_datetime(r.reported_on),
				"kind": "Damage",
				"reference": r.name,
				"detail": f"{r.status}: {r.description}",
			}
		)
	for r in frappe.get_all(
		"Rental Block", filters={"rental_unit": unit}, fields=["name", "from_datetime", "reason"]
	):
		events.append({"at": r.from_datetime, "kind": "Block", "reference": r.name, "detail": r.reason})
	return sorted(events, key=lambda e: get_datetime(e["at"]), reverse=True)


def asset_roi(company=None) -> list[dict]:
	filters = {"asset": ["is", "set"]}
	units = frappe.get_all("Rental Unit", filters=filters, fields=["name", "asset"])
	out = []
	for u in units:
		cost = flt(frappe.db.get_value("Asset", u.asset, "gross_purchase_amount"))
		conditions = "si.docstatus = 1 and i.rental_unit = %(unit)s"
		values = {"unit": u.name}
		if company:
			conditions += " and si.company = %(company)s"
			values["company"] = company
		revenue = frappe.db.sql(
			f"""select sum(i.base_net_amount) from `tabSales Invoice Item` i
			join `tabSales Invoice` si on si.name = i.parent where {conditions}""",
			values,
		)[0][0]
		revenue = flt(revenue)
		out.append(
			{
				"rental_unit": u.name,
				"asset": u.asset,
				"cost": cost,
				"revenue": revenue,
				"roi_pct": flt((revenue - cost) / cost * 100, 2) if cost else None,
			}
		)
	return out


def kpis(company=None, now=None) -> dict:
	"""Dashboard cards: units by status, live bookings, overdue returns, revenue this month, deposits held."""
	now = get_datetime(now or now_datetime())
	month_start = now.replace(day=1).date()
	units = frappe.get_all("Rental Unit", fields=["status", "count(name) as n"], group_by="status")
	deposits = frappe.db.sql("select sum(balance_held) from `tabRental Deposit`")[0][0]
	return {
		"units": {r.status: r.n for r in units},
		"active_bookings": frappe.db.count(
			"Rental Booking", {"docstatus": 1, "status": ["in", ("Confirmed", "Checked Out")]}
		),
		"checked_out": frappe.db.count("Rental Booking", {"docstatus": 1, "status": "Checked Out"}),
		"overdue_returns": len(overdue_returns(now)),
		"revenue_this_month": flt(sum(flt(r.revenue) for r in revenue(month_start, now.date(), company))),
		"deposits_held": flt(deposits),
	}

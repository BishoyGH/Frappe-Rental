"""Billing schedule generator (T22, docs/INVOICING.md D6). Pure: no database or frappe imports.

`generate(plan, start, end, total, ...)` turns a Rental Billing Plan (as a dict) into schedule rows
`{period_from, period_to, invoice_date, amount}`. Dates are `datetime.date`, `period_to` inclusive.

Plan keys (the Rental Billing Plan fields):
  frequency      One-off | Weekly | Monthly | Quarterly | Semi-annual | Yearly | Custom interval | Milestones
  interval, interval_unit   for Custom interval: every N "Days" or "Months"
  timing         In advance | In arrears | At check-in | At check-out | At confirmation
  first_invoice  At start date | At confirmation | Custom date (first_invoice_date)
  alignment      Rental anniversary | Calendar period start | Specific day of month (alignment_day)
  proration      None | Daily pro-rata | Full first period
  amount_basis   Rate x elapsed units | Fixed amount per period | Percent of total
  period_amount  amount for one full period (Fixed amount, or rate x units for one period)
  milestone_percents  "50, 50": Milestones split the total; milestone dates come from timing

Proration of partial periods (a period shorter than the nominal one, at either end):
  None             partial periods are charged as full periods
  Daily pro-rata   partial periods are charged by days covered / days in the nominal period
  Full first period  first partial period charged in full, last one pro-rata

When `period_amount` is empty the total is spread by the same weights, and the last row absorbs
rounding so the rows always add up to `total`.
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta

MONTH_STEPS = {"Monthly": 1, "Quarterly": 3, "Semi-annual": 6, "Yearly": 12}
RECURRING = {*MONTH_STEPS, "Weekly", "Custom interval"}


class BillingPlanError(ValueError):
	"""The plan cannot produce a schedule."""


def _round(value, precision: int) -> float:
	q = Decimal(1).scaleb(-precision)
	return float(Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP))


def _as_date(value) -> date:
	return date.fromisoformat(str(value)[:10]) if not isinstance(value, date) else value


def _step(plan: dict):
	"""Return (months, days) for one nominal period."""
	freq = plan.get("frequency")
	if freq in MONTH_STEPS:
		return MONTH_STEPS[freq], 0
	if freq == "Weekly":
		return 0, 7
	if freq == "Custom interval":
		n = int(plan.get("interval") or 0)
		if n < 1:
			raise BillingPlanError("Custom interval needs an interval of at least 1")
		return (n, 0) if plan.get("interval_unit", "Months") == "Months" else (0, n)
	raise BillingPlanError(f"Unknown frequency {freq!r}")


def _add(d: date, months: int, days: int, k: int = 1) -> date:
	return d + relativedelta(months=months * k) + timedelta(days=days * k)


def _first_boundary(start: date, plan: dict, months: int, days: int) -> date:
	"""First period start strictly after `start` for aligned plans, else start + one period."""
	alignment = plan.get("alignment") or "Rental anniversary"
	if alignment == "Rental anniversary":
		return _add(start, months, days)
	if alignment == "Calendar period start":
		if days:  # weekly-style: align to Monday
			return (
				start + timedelta(days=(7 - start.weekday()) % 7 or 7) if days == 7 else _add(start, 0, days)
			)
		anchor = date(start.year, 1, 1)
		while anchor <= start:
			anchor = _add(anchor, months, 0)
		return anchor
	if alignment == "Specific day of month":
		if not months:
			raise BillingPlanError("Specific day of month needs a month-based frequency")
		day = int(plan.get("alignment_day") or 1)
		if not 1 <= day <= 28:
			raise BillingPlanError("Alignment day must be between 1 and 28")
		anchor = start.replace(day=day)
		if anchor <= start:
			anchor = anchor + relativedelta(months=1)
		return anchor
	raise BillingPlanError(f"Unknown alignment {alignment!r}")


def periods(plan: dict, start: date, end: date) -> list[tuple[date, date, float]]:
	"""Split [start, end] (inclusive) into (from, to, weight); weight 1 = one full nominal period."""
	if end < start:
		raise BillingPlanError("End is before start")
	months, days = _step(plan)
	out = []
	first = _first_boundary(start, plan, months, days)
	anchor = (
		start
		if (plan.get("alignment") or "Rental anniversary") == "Rental anniversary"
		else _add(first, months, days, -1)
	)
	# Boundaries are counted from the first one, never stepped from the previous, so a 31st
	# anniversary stays on month end (31 Jan, 28 Feb, 31 Mar) instead of drifting to the 28th.
	k, cur = 0, start
	while cur <= end:
		boundary = _add(anchor, months, days, k + 1)
		nxt = min(boundary, end + timedelta(days=1))
		nominal_days = (boundary - _add(anchor, months, days, k)).days
		out.append((cur, nxt - timedelta(days=1), min((nxt - cur).days / nominal_days, 1.0)))
		cur, k = nxt, k + 1
	return out


def _weights(plan: dict, raw: list[float]) -> list[float]:
	proration = plan.get("proration") or "Daily pro-rata"
	if proration == "None":
		return [1.0] * len(raw)
	if proration == "Full first period":
		return [1.0, *raw[1:]] if raw else raw
	if proration == "Daily pro-rata":
		return raw
	raise BillingPlanError(f"Unknown proration {proration!r}")


def _invoice_date(plan, pf, pt, start, end, confirmed_on):
	timing = plan.get("timing") or "In advance"
	return {
		"In advance": pf,
		"In arrears": pt,
		"At check-in": start,
		"At check-out": end,
		"At confirmation": confirmed_on or start,
	}.get(timing) or _raise(f"Unknown timing {timing!r}")


def _raise(msg):
	raise BillingPlanError(msg)


def _split(amounts: list[float], total, precision: int) -> list[float]:
	"""Scale `amounts` to add up to total; last row absorbs rounding."""
	s = sum(amounts)
	if not s:
		return [0.0] * len(amounts)
	rows = [_round(total * a / s, precision) for a in amounts]
	rows[-1] = _round(total - sum(rows[:-1]), precision)
	return rows


def generate(
	plan: dict,
	start: date,
	end: date,
	total: float = 0,
	confirmed_on: date | None = None,
	precision: int = 2,
) -> list[dict]:
	freq = plan.get("frequency") or "One-off"
	basis = plan.get("amount_basis") or "Rate x elapsed units"

	if freq == "One-off":
		rows = [{"period_from": start, "period_to": end, "amount": _round(total, precision)}]
		rows[0]["invoice_date"] = _invoice_date(plan, start, end, start, end, confirmed_on)
	elif freq == "Milestones":
		pcts = [
			float(p)
			for p in str(plan.get("milestone_percents") or "").replace(";", ",").split(",")
			if p.strip()
		]
		if not pcts or abs(sum(pcts) - 100) > 1e-9:
			raise BillingPlanError("Milestone percents must add up to 100")
		amounts = _split(pcts, total, precision)
		# First milestone on the first invoice date, the rest spread to the end (last at check-out).
		span = (end - start).days
		rows = []
		for i, amt in enumerate(amounts):
			d = (
				start + timedelta(days=round(span * i / max(len(amounts) - 1, 1)))
				if len(amounts) > 1
				else start
			)
			rows.append({"period_from": start, "period_to": end, "invoice_date": d, "amount": amt})
	elif freq in RECURRING:
		parts = periods(plan, start, end)
		weights = _weights(plan, [w for _, _, w in parts])
		period_amount = plan.get("period_amount")
		if basis == "Percent of total":
			raise BillingPlanError("Percent of total is only for Milestones")
		if period_amount:
			amounts = [_round(float(period_amount) * w, precision) for w in weights]
		elif basis == "Fixed amount per period":
			raise BillingPlanError("Fixed amount per period needs a period amount")
		else:
			amounts = _split(weights, total, precision)
		rows = [
			{
				"period_from": pf,
				"period_to": pt,
				"invoice_date": _invoice_date(plan, pf, pt, start, end, confirmed_on),
				"amount": amt,
			}
			for (pf, pt, _), amt in zip(parts, amounts, strict=True)
		]
	else:
		raise BillingPlanError(f"Unknown frequency {freq!r}")

	first = plan.get("first_invoice") or "At start date"
	if rows and first == "At confirmation" and confirmed_on:
		rows[0]["invoice_date"] = min(rows[0]["invoice_date"], confirmed_on)
	elif rows and first == "Custom date":
		if not plan.get("first_invoice_date"):
			raise BillingPlanError("Custom first invoice needs a date")
		rows[0]["invoice_date"] = plan["first_invoice_date"]
	return rows


def regenerate(existing: list[dict], plan: dict, start, end, total, **kw) -> list[dict]:
	"""Rule 2: keep invoiced rows untouched, rebuild the rest for what is left of the period and total.

	Returns new un-invoiced rows. If invoiced rows already exceed the new total, one negative
	"Credit" row is returned so a credit note can be raised (posted invoices are never edited).
	"""
	locked = [r for r in existing if r.get("status") in ("Invoiced", "Paid", "Credited")]
	precision = kw.get("precision", 2)
	billed = sum(float(r.get("amount") or 0) for r in locked)
	billed_to = max((_as_date(r["period_to"]) for r in locked), default=None)
	remaining = _round(total - billed, precision)
	if remaining < 0:
		day = billed_to or start
		return [
			{
				"period_from": day,
				"period_to": day,
				"invoice_date": day,
				"amount": remaining,
				"adjustment_note": "Credit for invoiced amounts above the new total",
			}
		]
	new_start = billed_to + timedelta(days=1) if billed_to else start
	if new_start > end or not remaining:
		return []
	if plan.get("frequency") in ("One-off", "Milestones", None, ""):
		return generate({**plan, "frequency": "One-off"}, new_start, end, remaining, **kw)
	return generate(
		{**plan, "period_amount": None, "amount_basis": "Rate x elapsed units"},
		new_start,
		end,
		remaining,
		**kw,
	)

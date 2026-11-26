"""Provider scheduling (T45): working hours, slots, the provider's own view, Project and Timesheet.

- A Rental Schedule holds weekly slots (weekday, from, to) and an optional Holiday List. A Provider
  unit links one as `working_hours`; its bookings must fall inside one slot of one working day.
- `slots(unit, from_date, to_date, minutes)` offers free start times: the schedule's windows, minus
  holidays, minus busy rows in Rental Availability Cache (bookings, blocks, allocations), stepped
  by the schedule's `slot_minutes`.
- `my_schedule(user)` lists the bookings of the Provider units whose Employee is that user.
- `ensure_project(booking)` creates one ERPNext Project per submitted provider booking (linked by
  the custom field Project.rental_booking). Billable hours logged on Timesheets for that project
  become Rental Billable Events (type Timesheet) when the Timesheet is submitted, once per Timesheet.

Times are site-local wall-clock times, like booking datetimes.
"""

from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_datetime, get_time, getdate

from frappe_rental.services import availability, billable_events

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def validate_schedule(doc) -> None:
	if not doc.slots:
		frappe.throw(_("Add at least one working slot"))
	doc.slot_minutes = int(doc.slot_minutes or 60)
	if doc.slot_minutes < 5:
		frappe.throw(_("Slot length must be at least 5 minutes"))
	for row in doc.slots:
		if get_time(row.to_time) <= get_time(row.from_time):
			frappe.throw(_("Row {0}: To must be after From").format(row.idx))


def _schedule(unit: str):
	name = frappe.db.get_value("Rental Unit", unit, "working_hours")
	if not name:
		return None
	doc = frappe.get_cached_doc("Rental Schedule", name)
	return None if doc.disabled else doc


def _holidays(schedule, start, end) -> set:
	if not schedule.holiday_list:
		return set()
	return {
		getdate(d)
		for d in frappe.get_all(
			"Holiday",
			filters={
				"parent": schedule.holiday_list,
				"parenttype": "Holiday List",
				"holiday_date": ["between", [getdate(start), getdate(end)]],
			},
			pluck="holiday_date",
		)
	}


def windows(schedule, day) -> list[tuple[datetime, datetime]]:
	"""Working windows of one date, in order."""
	day = getdate(day)
	weekday = WEEKDAYS[day.weekday()]
	out = [
		(
			datetime.combine(day, get_time(r.from_time)),
			datetime.combine(day, get_time(r.to_time)),
		)
		for r in schedule.slots
		if r.weekday == weekday
	]
	return sorted(out)


def within_hours(unit: str, start, end) -> bool:
	"""True when [start, end) fits one working window of the unit (always True without a schedule)."""
	schedule = _schedule(unit)
	if not schedule:
		return True
	start, end = get_datetime(start), get_datetime(end)
	if getdate(start) in _holidays(schedule, start, start):
		return False
	return any(w0 <= start and end <= w1 for w0, w1 in windows(schedule, start))


def validate_booking(doc) -> None:
	"""Booking hook: lines on Provider units must sit inside working hours and off holidays."""
	for line in doc.get("lines") or []:
		if not line.rental_unit:
			continue
		start = line.get("from_datetime") or doc.from_datetime
		end = line.get("to_datetime") or doc.to_datetime
		if start and end and not within_hours(line.rental_unit, start, end):
			frappe.throw(
				_("Row {0}: {1} does not work at that time").format(line.idx, line.rental_unit),
				availability.UnavailableError,
			)


def slots(unit: str, from_date, to_date=None, minutes: int = 60) -> list[dict]:
	"""Free start times of `minutes` length between two dates (inclusive)."""
	schedule = _schedule(unit)
	if not schedule:
		frappe.throw(_("{0} has no working hours").format(unit))
	minutes = int(minutes or 60)
	if minutes < 5:
		frappe.throw(_("Duration must be at least 5 minutes"))
	from_date, to_date = getdate(from_date), getdate(to_date or from_date)
	if (to_date - from_date).days > 62:
		frappe.throw(_("Ask for at most 62 days at a time"))
	step = timedelta(minutes=int(schedule.slot_minutes or 60))
	length = timedelta(minutes=minutes)
	holidays = _holidays(schedule, from_date, to_date)
	busy = availability.overlapping_rows(
		unit, datetime.combine(from_date, datetime.min.time()), get_datetime(add_days(to_date, 1))
	)
	busy = [
		(get_datetime(r["busy_from"]), get_datetime(r["busy_to"]) if r.get("busy_to") else None) for r in busy
	]
	out, day = [], from_date
	while day <= to_date:
		if day not in holidays:
			for w0, w1 in windows(schedule, day):
				t = w0
				while t + length <= w1:
					end = t + length
					if not any(b0 < end and (b1 is None or b1 > t) for b0, b1 in busy):
						out.append({"from_datetime": t, "to_datetime": end})
					t += step
		day = add_days(day, 1)
	return out


def provider_units(user: str) -> list[str]:
	employees = frappe.get_all("Employee", filters={"user_id": user}, pluck="name")
	if not employees:
		return []
	return frappe.get_all(
		"Rental Unit", filters={"unit_type": "Provider", "employee": ["in", employees]}, pluck="name"
	)


def my_schedule(user: str, from_date, to_date) -> list[dict]:
	"""Bookings of the user's own Provider units in a date range, with their project."""
	units = provider_units(user)
	if not units:
		return []
	lines = frappe.get_all(
		"Rental Booking Line",
		filters={"rental_unit": ["in", units], "parenttype": "Rental Booking"},
		fields=["parent", "rental_unit"],
	)
	names = sorted({line.parent for line in lines})
	if not names:
		return []
	rows = frappe.get_all(
		"Rental Booking",
		filters={
			"name": ["in", names],
			"docstatus": ["<", 2],
			"from_datetime": ["<", get_datetime(add_days(to_date, 1))],
			"to_datetime": [">", get_datetime(from_date)],
		},
		fields=["name", "customer", "customer_name", "from_datetime", "to_datetime", "status"],
		order_by="from_datetime asc",
	)
	unit_of = {line.parent: line.rental_unit for line in lines}
	for row in rows:
		row["rental_unit"] = unit_of.get(row.name)
		row["project"] = frappe.db.get_value("Project", {"rental_booking": row.name})
	return rows


def is_provider_booking(doc) -> bool:
	units = [line.rental_unit for line in doc.get("lines") or [] if line.rental_unit]
	return bool(units) and bool(
		frappe.db.exists("Rental Unit", {"name": ["in", units], "unit_type": "Provider"})
	)


def ensure_project(doc) -> str | None:
	"""One Project per provider booking; safe to run twice."""
	if not is_provider_booking(doc):
		return None
	existing = frappe.db.get_value("Project", {"rental_booking": doc.name})
	if existing:
		return existing
	project = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"{doc.name} {doc.get('customer_name') or doc.customer}"[:140],
			"customer": doc.customer,
			"company": doc.company,
			"expected_start_date": getdate(doc.from_datetime),
			"expected_end_date": getdate(doc.to_datetime) if doc.to_datetime else None,
			"rental_booking": doc.name,
		}
	)
	project.flags.ignore_permissions = True  # created by the booking's submit, which was permission-checked
	project.insert()
	return project.name


def bill_timesheet(timesheet) -> list[str]:
	"""Queue the billable amount of a submitted Timesheet's rental project as one Billable Event.

	Idempotent per Timesheet (the event's source). A Timesheet is expected to log one rental project;
	hours for a second rental project on the same Timesheet are refused at submit.
	"""
	if timesheet.docstatus != 1:
		return []
	totals = {}
	for log in timesheet.time_logs:
		if not log.project or not log.get("is_billable"):
			continue
		totals[log.project] = totals.get(log.project, 0) + flt(log.billing_amount)
	rental = [p for p in totals if frappe.db.get_value("Project", p, "rental_booking")]
	if len(rental) > 1:
		frappe.throw(_("Log hours for one rental booking per Timesheet"))
	out = []
	for project, amount in totals.items():
		booking = frappe.db.get_value("Project", project, "rental_booking")
		if not booking or amount <= 0:
			continue
		out.append(
			billable_events.add(
				booking,
				"Timesheet",
				amount,
				_("Billable hours on {0}").format(timesheet.name),
				source=timesheet,
				event_date=getdate(timesheet.get("end_date") or timesheet.get("start_date")),
			)
		)
	return out


def on_timesheet_submit(doc, method=None) -> None:
	bill_timesheet(doc)

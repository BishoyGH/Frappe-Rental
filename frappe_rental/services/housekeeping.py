"""Housekeeping and turnaround (T51).

- When a unit comes back in Good condition on a Rental Type with `housekeeping_task`, the return
  creates one Rental Housekeeping Task (Cleaning) per unit and sets the unit to Turnaround. The task is
  due at the return time plus the type's `buffer_after` (60 minutes when the type has none).
- The buffer already keeps the next booking away during that time (T13). If the task is still open
  when it falls due, the hourly `check_overdue` adds an open-ended Rental Block (reason Cleaning), so
  the unit cannot be booked until someone finishes the job.
- Marking the task Done (or Cancelled) ends that block at the completion time and returns the unit to
  Available. Cancelling the return removes its open tasks. Every step is safe to run twice.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime

DOCTYPE = "Rental Housekeeping Task"
CLOSED = ("Done", "Cancelled")


def _enabled(booking) -> bool:
	return bool(frappe.db.get_value("Rental Type", booking.rental_type, "housekeeping_task"))


def on_return(doc, booking) -> list[str]:
	"""Return handover submitted: one task per unit returned in Good condition."""
	if not _enabled(booking):
		return []
	after = cint(frappe.db.get_value("Rental Type", booking.rental_type, "buffer_after")) or 60
	due = get_datetime(doc.posted_on or now_datetime()) + timedelta(minutes=after)
	made = []
	for line in doc.lines:
		if not line.rental_unit or line.condition != "Good":
			continue
		if frappe.db.get_value("Rental Unit", line.rental_unit, "identification_mode") == "Pooled":
			continue
		existing = frappe.db.get_value(
			DOCTYPE, {"rental_handover": doc.name, "rental_unit": line.rental_unit}
		)
		if existing:
			made.append(existing)
			continue
		task = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"rental_unit": line.rental_unit,
				"task_type": "Cleaning",
				"status": "Open",
				"due_by": due,
				"rental_booking": booking.name,
				"rental_handover": doc.name,
			}
		)
		task.flags.ignore_permissions = True  # created by a permitted return
		task.insert()
		frappe.db.set_value("Rental Unit", line.rental_unit, "status", "Turnaround")
		made.append(task.name)
	return made


def on_return_cancel(doc) -> None:
	for name in frappe.get_all(
		DOCTYPE, filters={"rental_handover": doc.name, "status": ["not in", CLOSED]}, pluck="name"
	):
		task = frappe.get_doc(DOCTYPE, name)
		_end_block(task, now_datetime())
		frappe.delete_doc(DOCTYPE, name, ignore_permissions=True)  # part of the permitted cancel


def complete(task_name: str, notes: str | None = None) -> None:
	task = frappe.get_doc(DOCTYPE, task_name)
	if task.status in CLOSED:
		return
	task.status = "Done"
	if notes:
		task.notes = notes
	task.save()


def on_task_update(task) -> None:
	if task.status not in CLOSED:
		return
	if not task.completed_on:
		task.db_set("completed_on", now_datetime(), update_modified=False)
	_end_block(task, get_datetime(task.completed_on))
	still_open = frappe.db.exists(
		DOCTYPE, {"rental_unit": task.rental_unit, "status": ["not in", CLOSED], "name": ["!=", task.name]}
	)
	if not still_open and frappe.db.get_value("Rental Unit", task.rental_unit, "status") == "Turnaround":
		frappe.db.set_value("Rental Unit", task.rental_unit, "status", "Available")


def _end_block(task, when) -> None:
	if not task.rental_block or not frappe.db.exists("Rental Block", task.rental_block):
		return
	block = frappe.get_doc("Rental Block", task.rental_block)
	if block.to_datetime:
		return
	block.to_datetime = max(get_datetime(when), get_datetime(block.from_datetime) + timedelta(minutes=1))
	block.flags.ignore_permissions = True  # closing the system's own overdue block
	block.save()


def check_overdue(now=None) -> int:
	"""Scheduler (hourly): block units whose turnaround task is overdue. Returns blocks added."""
	now = get_datetime(now or now_datetime())
	tasks = frappe.get_all(
		DOCTYPE,
		filters={"status": ["not in", CLOSED], "due_by": ["<", now], "rental_block": ["is", "not set"]},
		fields=["name", "rental_unit", "due_by"],
	)
	for t in tasks:
		block = frappe.get_doc(
			{
				"doctype": "Rental Block",
				"rental_unit": t.rental_unit,
				"reason": "Cleaning",
				"from_datetime": t.due_by,
				"to_datetime": None,
				"notes": _("Turnaround task {0} is overdue").format(t.name),
			}
		)
		block.flags.ignore_permissions = True  # system block until the overdue task is done
		block.insert()
		frappe.db.set_value(DOCTYPE, t.name, "rental_block", block.name, update_modified=False)
	return len(tasks)

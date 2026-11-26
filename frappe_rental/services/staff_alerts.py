"""Staff alerts (T38): in-app Notification Log entries, and optional email, by role for chosen rental events.

Rules are rows of Rental Settings > Alert rules (event, role, in_app, email). While that table is empty the
defaults below apply, so alerts work out of the box: in-app on, email off. ``dispatch`` runs from
``events.emit``, which fires each event once, so a rerun of the code that raised the event never alerts twice.
An alert that cannot be delivered is logged and never breaks the business action that raised it.
"""

import frappe
from frappe import _
from frappe.utils import cint

ALERT_EVENTS = (
	"damage_reported",
	"sla_breached",
	"housekeeping_overdue",
	"overdue",
	"contract_signed",
	"contract_notice",
)

REFERENCES = ("Rental Damage Report", "Rental Contract", "Rental Housekeeping Task", "Rental Booking")

DEFAULT_RULES = (
	("damage_reported", "Rental Manager"),
	("damage_reported", "Rental Admin"),
	("sla_breached", "Rental Manager"),
	("sla_breached", "Rental Admin"),
	("housekeeping_overdue", "Rental Manager"),
	("housekeeping_overdue", "Rental Agent"),
	("overdue", "Rental Manager"),
	("overdue", "Rental Agent"),
	("contract_signed", "Rental Manager"),
	("contract_notice", "Rental Manager"),
)


def subject(event: str, log) -> str:
	ref = log.reference_name
	return {
		"damage_reported": _("Damage reported: {0}"),
		"sla_breached": _("SLA breached on contract {0}"),
		"housekeeping_overdue": _("Housekeeping overdue: {0}"),
		"overdue": _("Return overdue: booking {0}"),
		"contract_signed": _("Contract signed: {0}"),
		"contract_notice": _("Contract notice period started: {0}"),
	}[event].format(ref)


def rules() -> list[dict]:
	"""The alert rules in force: the saved table, or the defaults when nothing was saved."""
	rows = frappe.get_all(
		"Rental Alert Rule",
		filters={"parent": "Rental Settings", "parenttype": "Rental Settings"},
		fields=["event", "role", "in_app", "email"],
		order_by="idx",
	)
	if rows:
		return rows
	return [{"event": e, "role": r, "in_app": 1, "email": 0} for e, r in DEFAULT_RULES]


def users_with_role(role: str) -> list[str]:
	users = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
	if not users:
		return []
	return frappe.get_all(
		"User",
		filters={"name": ["in", users], "enabled": 1, "user_type": "System User"},
		pluck="name",
	)


def dispatch(log) -> None:
	if log.event not in ALERT_EVENTS:
		return
	try:
		_dispatch(log)
	except Exception:
		frappe.log_error(title="Rental staff alert failed")


def _dispatch(log) -> None:
	text = subject(log.event, log)
	in_app: set[str] = set()
	email: set[str] = set()
	for rule in rules():
		if rule["event"] != log.event:
			continue
		users = users_with_role(rule["role"])
		if cint(rule["in_app"]):
			in_app.update(users)
		if cint(rule["email"]):
			email.update(users)
	for user in sorted(in_app):
		alert = frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"subject": text,
				"document_type": log.reference_doctype,
				"document_name": log.reference_name,
			}
		)
		alert.flags.ignore_permissions = True  # a system alert addressed to a user chosen by role
		alert.insert()
	if email:
		frappe.sendmail(recipients=sorted(email), subject=text, message=text, now=False)


def my_alerts(limit: int = 20) -> list[dict]:
	"""The session user's recent rental alerts, newest first."""
	return frappe.get_all(
		"Notification Log",
		filters={
			"for_user": frappe.session.user,
			"type": "Alert",
			"document_type": ["in", list(REFERENCES)],
		},
		fields=["name", "subject", "document_type", "document_name", "read", "creation"],
		order_by="creation desc",
		limit=limit,
	)


def save_rules(rows: list[dict]) -> list[dict]:
	"""Replace the alert rules (Rental Settings write access required)."""
	clean = []
	for row in rows:
		if row.get("event") not in ALERT_EVENTS:
			frappe.throw(_("Unknown alert event {0}").format(row.get("event")))
		if not frappe.db.exists("Role", row.get("role")):
			frappe.throw(_("Unknown role {0}").format(row.get("role")))
		clean.append(
			{
				"event": row["event"],
				"role": row["role"],
				"in_app": 1 if cint(row.get("in_app", 1)) else 0,
				"email": 1 if cint(row.get("email")) else 0,
			}
		)
	settings = frappe.get_single("Rental Settings")
	settings.set("alert_rules", clean)
	settings.save()
	return rules()

"""Staff alert settings and the user's own alerts (T38)."""

import frappe
from frappe import _

from frappe_rental.services import staff_alerts


def _staff() -> None:
	if not frappe.has_permission("Rental Booking", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist(methods=["GET", "POST"])
def get() -> dict:
	"""The rules in force, the events and roles they can use, and the caller's recent alerts."""
	_staff()
	return {
		"rules": staff_alerts.rules(),
		"events": list(staff_alerts.ALERT_EVENTS),
		"roles": frappe.get_all(
			"Role", filters={"name": ["like", "Rental %"]}, pluck="name", order_by="name"
		),
		"can_edit": bool(frappe.has_permission("Rental Settings", "write")),
		"alerts": staff_alerts.my_alerts(),
	}


@frappe.whitelist(methods=["POST"])
def save(rules: str | list) -> list[dict]:
	if not frappe.has_permission("Rental Settings", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return staff_alerts.save_rules(frappe.parse_json(rules))


@frappe.whitelist(methods=["POST"])
def mark_read(name: str) -> None:
	_staff()
	if frappe.db.get_value("Notification Log", name, "for_user") != frappe.session.user:
		frappe.throw(_("Not found"), frappe.DoesNotExistError)
	frappe.db.set_value("Notification Log", name, "read", 1)

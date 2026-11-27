"""Staff alerts (T38): default in-app alerts by role, configurable rules, optional email."""

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime, random_string

from frappe_rental.api import alerts as api
from frappe_rental.services import events, staff_alerts, visits
from frappe_rental.tests.test_contract_views import active


def staff_user(role: str) -> str:
	email = f"t38-{random_string(6)}@example.com".lower()
	frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "T38",
			"send_welcome_email": 0,
			"roles": [{"role": role}],
		}
	).insert(ignore_permissions=True)  # test fixture
	return email


def unread(user: str, name: str) -> list[str]:
	return frappe.get_all(
		"Notification Log", filters={"for_user": user, "document_name": name}, pluck="subject"
	)


class TestStaffAlerts(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Rental Alert Rule")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Rental Alert Rule")

	def test_defaults_alert_managers_in_app_only(self):
		manager, agent = staff_user("Rental Manager"), staff_user("Rental Agent")
		doc = active(sla_response_hours=1, sla_resolution_hours=2)
		with patch.object(frappe, "sendmail") as mail:
			events.emit("sla_breached", doc, key="v1")
			events.emit("sla_breached", doc, key="v1")  # fires once
		self.assertEqual(len(unread(manager, doc.name)), 1)
		self.assertIn(doc.name, unread(manager, doc.name)[0])
		self.assertEqual(unread(agent, doc.name), [])  # not a default recipient of SLA alerts
		mail.assert_not_called()

	def test_scheduler_breach_alerts_once(self):
		manager = staff_user("Rental Manager")
		doc = active(sla_response_hours=1, sla_resolution_hours=2)
		visits.request_service(doc, "Broken")
		later = now_datetime() + timedelta(hours=5)
		self.assertEqual(visits.check_sla(later), 1)
		self.assertEqual(visits.check_sla(later), 0)
		self.assertEqual(len(unread(manager, doc.name)), 1)

	def test_rules_are_configurable_with_optional_email(self):
		agent = staff_user("Rental Agent")
		manager = staff_user("Rental Manager")
		api.save(
			[
				{"event": "sla_breached", "role": "Rental Agent", "in_app": 1, "email": 1},
				{"event": "overdue", "role": "Rental Manager", "in_app": 0, "email": 0},
			]
		)
		doc = active(sla_response_hours=1, sla_resolution_hours=2)
		with patch.object(frappe, "sendmail") as mail:
			events.emit("sla_breached", doc, key="v2")
		self.assertEqual(len(unread(agent, doc.name)), 1)
		self.assertEqual(unread(manager, doc.name), [])
		self.assertIn(agent, mail.call_args.kwargs["recipients"])
		frappe.set_user(agent)
		got = api.get()
		self.assertEqual([a["document_name"] for a in got["alerts"]], [doc.name])
		self.assertFalse(got["can_edit"])
		api.mark_read(got["alerts"][0]["name"])
		with self.assertRaises(frappe.PermissionError):
			api.save([])
		with self.assertRaises(frappe.PermissionError):
			frappe.set_user("Guest") or api.get()

	def test_rejects_unknown_event_or_role(self):
		with self.assertRaises(frappe.ValidationError):
			api.save([{"event": "nope", "role": "Rental Agent"}])
		with self.assertRaises(frappe.ValidationError):
			api.save([{"event": "overdue", "role": "No Such Role"}])
		self.assertEqual({r["event"] for r in staff_alerts.rules()}, set(staff_alerts.ALERT_EVENTS))

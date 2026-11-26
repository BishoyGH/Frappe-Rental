import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.www import rental


def make_user(*roles):
	email = f"t17-{random_string(6).lower()}@example.com"
	user = frappe.get_doc(
		{"doctype": "User", "email": email, "first_name": "T17", "send_welcome_email": 0}
	).insert()
	if roles:
		user.add_roles(*roles)
	return email


class TestStaffApp(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_route_rule(self):
		rules = frappe.get_hooks("website_route_rules")
		self.assertIn({"from_route": "/rental/<path:app_path>", "to_route": "rental"}, rules)

	def test_guest_redirected_to_login(self):
		frappe.set_user("Guest")
		frappe.local.flags.redirect_location = None
		with self.assertRaises(frappe.Redirect):
			rental.get_context(frappe._dict())
		self.assertTrue(frappe.local.flags.redirect_location.startswith("/login?redirect-to="))

	def test_user_without_rental_role_is_refused(self):
		frappe.set_user(make_user())
		self.assertFalse(rental.has_app_access())
		with self.assertRaises(frappe.PermissionError):
			rental.get_context(frappe._dict())

	def test_rental_agent_gets_boot(self):
		frappe.set_user(make_user("Rental Agent"))
		context = rental.get_context(frappe._dict())
		self.assertTrue(context.boot["csrf_token"])
		self.assertEqual(context.boot["rental_boot"]["roles"], ["Rental Agent"])
		self.assertEqual(context.boot["rental_boot"]["user"], frappe.session.user)

	def test_staff_roles_cover_matrix(self):
		self.assertTrue({"Rental Admin", "Rental Agent", "System Manager"} <= rental.STAFF_ROLES)

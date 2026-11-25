import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_rental.services.permissions import MATRIX, PERMS
from frappe_rental.services.setup import ROLES, create_roles

ROLES_UNDER_TEST = ROLES  # admin, manager, agent, provider, accountant, customer


def user_with_role(role: str) -> str:
	email = f"t09-{frappe.scrub(role)}@example.com"
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": role,
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		).insert(ignore_permissions=True)  # test fixture
	return email


class TestPermissionMatrix(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		create_roles()

	def test_doctype_json_matches_matrix(self):
		for doctype, roles in MATRIX.items():
			meta = frappe.get_meta(doctype)
			actual = {
				p.role: "".join(ch for ch, field in PERMS.items() if p.get(field))
				for p in meta.permissions
				if p.permlevel == 0
			}
			self.assertEqual(actual, roles, doctype)

	def test_matrix_per_role(self):
		for role in ROLES_UNDER_TEST:
			user = user_with_role(role)
			for doctype, roles in MATRIX.items():
				allowed = roles.get(role, "")
				for ch, ptype in PERMS.items():
					with self.subTest(role=role, doctype=doctype, ptype=ptype):
						got = frappe.has_permission(doctype, ptype, user=user)
						self.assertEqual(bool(got), ch in allowed)

	def test_workspace_and_cards(self):
		self.assertTrue(frappe.db.exists("Workspace", "Rental"))
		for card in ("Available Units", "Published Rental Items"):
			self.assertTrue(frappe.db.exists("Number Card", card))
		shortcuts = {s.link_to for s in frappe.get_doc("Workspace", "Rental").shortcuts}
		self.assertTrue(set(MATRIX) <= shortcuts)

import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_rental.tests.utils import make_company


def make_location(name, company, parent=None, is_group=0, timezone="Europe/Berlin"):
	if frappe.db.exists("Rental Location", name):
		return frappe.get_doc("Rental Location", name)
	return frappe.get_doc(
		{
			"doctype": "Rental Location",
			"location_name": name,
			"company": company,
			"parent_rental_location": parent,
			"is_group": is_group,
			"timezone": timezone,
		}
	).insert()


class TestRentalLocation(FrappeTestCase):
	def setUp(self):
		self.company = make_company()
		frappe.set_user("Administrator")

	def test_tree_and_cost_center(self):
		root = make_location("T05 Root", self.company, is_group=1)
		child = make_location("T05 Child", self.company, parent=root.name)
		child.reload()
		self.assertEqual(child.parent_rental_location, root.name)
		self.assertTrue(child.cost_center)
		self.assertTrue(frappe.db.exists("Cost Center", child.cost_center))
		# idempotent
		from frappe_rental.services.location import ensure_cost_center

		self.assertEqual(ensure_cost_center(child), child.cost_center)

	def test_invalid_timezone_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_location("T05 Bad TZ", self.company, timezone="Mars/Olympus")

	def test_user_permission_by_location(self):
		a = make_location("T05 Branch A", self.company)
		b = make_location("T05 Branch B", self.company)
		email = "t05-agent@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "T05",
					"send_welcome_email": 0,
					"roles": [{"role": "Rental Agent"}],
				}
			).insert()
		frappe.get_doc(
			{"doctype": "User Permission", "user": email, "allow": "Rental Location", "for_value": a.name}
		).insert(ignore_if_duplicate=True)
		frappe.clear_cache(user=email)
		self.assertTrue(frappe.has_permission("Rental Location", "read", doc=a.name, user=email))
		self.assertFalse(frappe.has_permission("Rental Location", "read", doc=b.name, user=email))

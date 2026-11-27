"""Release checks (T60): the upgrade path (every migrate re-runs install) is idempotent, and the version is recorded."""

import pathlib
import re

import frappe
from frappe.tests.utils import FrappeTestCase

import frappe_rental
from frappe_rental import install

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


class TestRelease(FrappeTestCase):
	def counts(self):
		return {
			dt: frappe.db.count(dt)
			for dt in ("Custom Field", "Notification", "Account", "Warehouse", "Rental Alert Rule", "Role")
		}

	def test_after_install_can_run_on_every_migrate(self):
		install.after_install()
		before = self.counts()
		install.after_install()  # what `bench migrate` does on every upgrade
		self.assertEqual(self.counts(), before)

	def test_version_is_semver_and_in_the_changelog(self):
		self.assertRegex(frappe_rental.__version__, r"^\d+\.\d+\.\d+$")
		changelog = (ROOT / "CHANGELOG.md").read_text()
		self.assertTrue(re.search(rf"^## {re.escape(frappe_rental.__version__)}\b", changelog, re.M))

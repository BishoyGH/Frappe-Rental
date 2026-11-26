"""Composite indexes (T55) exist after migrate and re-applying them is harmless."""

import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_rental.services import indexes


def _indexed_columns(doctype):
	"""Column lists of the table's indexes (MariaDB or Postgres)."""
	table = f"tab{doctype}"
	if frappe.db.db_type == "postgres":
		rows = frappe.db.sql("select indexdef from pg_indexes where tablename = %s", table)
		return [r[0] for r in rows]
	rows = frappe.db.sql(f"show index from `{table}`", as_dict=True)
	out = {}
	for r in rows:
		out.setdefault(r["Key_name"], []).append(r["Column_name"])
	return [",".join(v) for v in out.values()]


class TestIndexes(FrappeTestCase):
	def test_indexes_present_and_idempotent(self):
		for doctype, groups in indexes.INDEXES.items():
			indexes.apply(doctype)
			indexes.apply(doctype)  # twice is fine
			found = _indexed_columns(doctype)
			for fields in groups:
				if frappe.db.db_type == "postgres":
					self.assertTrue(any(all(f in d for f in fields) for d in found), (doctype, fields))
				else:
					self.assertIn(",".join(fields), found, doctype)

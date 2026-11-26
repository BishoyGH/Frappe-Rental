import importlib
import pkgutil
import re
import tempfile
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase  # path valid on v15 and v16

import frappe_rental
from frappe_rental import compat
from frappe_rental.compat.frappe import _parse

PATTERN = re.compile(r"frappe\.__version__|\bIS_V1[56]\b|frappe_version\(|frappe_major\(")


def find_violations(root: Path) -> list[str]:
	"""Files outside compat/ and tests/ that check the Frappe version directly."""
	out = []
	for path in root.rglob("*.py"):
		if path.relative_to(root).parts[0] in ("compat", "tests"):
			continue
		if PATTERN.search(path.read_text()):
			out.append(str(path))
	return out


class TestCompat(FrappeTestCase):
	def test_imports_every_compat_module(self):
		for mod in pkgutil.iter_modules(compat.__path__):
			importlib.import_module(f"frappe_rental.compat.{mod.name}")

	def test_flags_match_version(self):
		self.assertNotEqual(compat.IS_V15, compat.IS_V16)
		self.assertEqual(compat.frappe_version()[0], compat.frappe_major())

	def test_parse(self):
		self.assertEqual(_parse("16.61.0"), (16, 61, 0))
		self.assertEqual(_parse("15.0.0-beta.1"), (15, 0, 0))
		self.assertEqual(_parse("16.0.0-dev"), (16, 0, 0))
		self.assertEqual(_parse("16"), (16, 0, 0))

	def test_no_version_checks_outside_compat(self):
		self.assertEqual(find_violations(Path(frappe_rental.__file__).parent), [])

	def test_violation_is_detected(self):
		with tempfile.TemporaryDirectory() as d:
			root = Path(d)
			(root / "services").mkdir()
			(root / "services" / "bad.py").write_text("import frappe\nx = frappe.__version__\n")
			(root / "compat").mkdir()
			(root / "compat" / "ok.py").write_text("import frappe\nx = frappe.__version__\n")
			self.assertEqual(len(find_violations(root)), 1)


class TestErpnextShim(FrappeTestCase):
	def test_ensure_setup_complete_returns_existing_company(self):
		import frappe

		from frappe_rental.compat.erpnext import ensure_setup_complete

		company = ensure_setup_complete()
		self.assertTrue(frappe.db.exists("Company", company))
		self.assertEqual(ensure_setup_complete(), company)  # idempotent


class TestSerialSwitch(FrappeTestCase):
	def test_enable_serial_numbers(self):
		from frappe_rental.compat.erpnext import enable_serial_numbers

		enable_serial_numbers()
		field = "enable_serial_and_batch_no_for_item"
		if frappe.get_meta("Stock Settings").has_field(field):
			self.assertEqual(frappe.db.get_single_value("Stock Settings", field), 1)
		enable_serial_numbers()  # idempotent

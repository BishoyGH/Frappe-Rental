"""List the translatable strings of the app (T57): Vue ``__('...')``, Python ``_("...")`` and Jinja ``_('...')``.

``python scripts/extract_messages.py`` prints them, one per line, as JSON-escaped text.
``python scripts/extract_messages.py --check ar`` exits 1 if a customer-facing string has no translation in
``frappe_rental/translations/ar.csv`` (customer-facing: public site, booking flow, portal, contracts).
"""

import csv
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "frappe_rental"
VUE = re.compile(r"""__\(\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"|`([^`$]*)`)""")
PY = re.compile(r"""\b_\(\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""")
JINJA = re.compile(r"""\{\{\s*_\(\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")""")
CUSTOMER = (
	"frontend/src/pages/BookFlow.vue",
	"frontend/src/pages/MyBookings.vue",
	"frontend/src/pages/MyBookingDetail.vue",
	"frontend/src/pages/MyContracts.vue",
	"frontend/src/pages/MyContractDetail.vue",
	"frappe_rental/www/",
	"frappe_rental/api/checkout.py",
	"frappe_rental/api/portal.py",
	"frappe_rental/api/public.py",
	"frappe_rental/services/checkout.py",
	"frappe_rental/services/portal.py",
	"frappe_rental/services/public_site.py",
	"frappe_rental/services/payments.py",
	"frappe_rental/services/esign.py",
)


def scan(path: pathlib.Path, pattern: re.Pattern) -> set[str]:
	found = set()
	for m in pattern.finditer(path.read_text(errors="ignore")):
		text = next(g for g in m.groups() if g is not None)
		found.add(bytes(text, "utf-8").decode("unicode_escape") if "\\" in text else text)
	return found


def messages(only_customer: bool = False) -> set[str]:
	out: set[str] = set()
	files = [(p, VUE) for p in (ROOT / "frontend/src").rglob("*.vue") if "node_modules" not in p.parts] + [
		(p, VUE) for p in (ROOT / "frontend/src").rglob("*.js")
	]
	files += [(p, PY) for p in APP.rglob("*.py") if "tests" not in p.parts]
	files += [(p, JINJA) for p in (APP / "www").rglob("*.html")]
	for path, pattern in files:
		rel = str(path.relative_to(ROOT))
		if only_customer and not rel.startswith(CUSTOMER):
			continue
		out |= scan(path, pattern)
	return out


def translated(lang: str) -> set[str]:
	with open(APP / "translations" / f"{lang}.csv", newline="") as f:
		return {row[0] for row in csv.reader(f) if len(row) >= 2 and row[1].strip()}


if __name__ == "__main__":
	if "--check" in sys.argv:
		lang = sys.argv[sys.argv.index("--check") + 1]
		missing = sorted(messages(only_customer=True) - translated(lang))
		for m in missing:
			print(json.dumps(m, ensure_ascii=False))
		print(f"{len(missing)} customer-facing strings without {lang} translation", file=sys.stderr)
		sys.exit(1 if missing else 0)
	for m in sorted(messages()):
		print(json.dumps(m, ensure_ascii=False))

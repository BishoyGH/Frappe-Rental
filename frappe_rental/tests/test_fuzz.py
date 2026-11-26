"""Input fuzzing of the guest endpoints (T56): hostile input gets a clean Frappe error, never a crash or a leak."""

import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_rental.api import checkout as checkout_api
from frappe_rental.api import public as public_api
from frappe_rental.tests.test_public_site import TestPublicSite

HOSTILE = [
	None,
	"",
	" ",
	"x" * 5000,
	"' OR 1=1 --",
	"1; DROP TABLE tabUser",
	'"><script>alert(1)</script>',
	"../../etc/passwd",
	"\x00",
	"{{7*7}}",
	"-1",
	"9" * 40,
	"2027-13-45 99:99",
	[],
	{},
	{"item": {"$ne": 1}},
	-5,
	1e308,
]

# Errors a caller can get: all are Frappe exceptions with a safe message (HTTP 4xx), none is a bare Exception
CLEAN = (
	frappe.exceptions.FrappeTypeError,  # Frappe's own argument type check on whitelisted methods
	frappe.ValidationError,
	frappe.PermissionError,
	frappe.DoesNotExistError,
	frappe.DuplicateEntryError,
)


class TestFuzz(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Guest")

	def tearDown(self):
		frappe.set_user("Administrator")

	def attempt(self, fn, *args, **kwargs):
		try:
			out = fn(*args, **kwargs)
		except CLEAN:
			return
		except (TypeError, AttributeError, ValueError) as e:
			self.fail(f"{fn.__module__}.{fn.__name__}{args} crashed with {type(e).__name__}: {e}")
		self.assertNotIn("traceback", str(out).lower())

	def test_public_endpoints_survive_hostile_input(self):
		for bad in HOSTILE:
			self.attempt(public_api.items, rental_type=bad)
			self.attempt(public_api.items, location=bad, from_datetime=bad, to_datetime=bad)
			self.attempt(public_api.items, qty=bad, guests=bad, start=bad)
			self.attempt(public_api.quote, bad, bad, bad)
			self.attempt(public_api.quote, "x", "2027-01-01 10:00", "2027-01-02 10:00", bad)
			self.attempt(public_api.calendar, bad, bad)
			self.attempt(checkout_api.extras, bad)

	def test_checkout_start_survives_hostile_input(self):
		for bad in HOSTILE:
			self.attempt(checkout_api.start, bad)
			self.attempt(checkout_api.start, {"item": bad, "from_datetime": bad, "to_datetime": bad})
			self.attempt(checkout_api.start, {"details": bad, "extras": bad})
			self.attempt(checkout_api.start, {"details": {"email": bad, "full_name": bad}})
		for text in ("not json", "[1,2", "{" * 50):
			self.attempt(checkout_api.start, text)


class TestFuzzRealItem(TestPublicSite):
	"""Same hostile values, but against a published item so the deeper code paths run."""

	test_lists_published_only_with_price_for_dates = None  # inherited tests are not repeated here
	test_calendar_and_quote = None

	@staticmethod
	def calls(item, bad):
		start = {"item": item, "from_datetime": "2027-01-01 10:00", "to_datetime": "2027-01-01 12:00"}
		return [
			lambda: public_api.quote(item, bad, bad),
			lambda: public_api.quote(item, "2027-01-01 10:00", bad),
			lambda: public_api.quote(item, "2027-01-01 10:00", "2027-01-01 12:00", bad),
			lambda: public_api.calendar(item, bad),
			lambda: checkout_api.start({"item": item, "from_datetime": bad, "to_datetime": bad}),
			lambda: checkout_api.start({**start, "details": {"full_name": bad, "email": bad}}),
		]

	def test_hostile_dates_and_quantities(self):
		item = self.item().name
		frappe.set_user("Guest")
		try:
			for bad in HOSTILE:
				for call in self.calls(item, bad):
					try:
						call()
					except CLEAN:
						pass
					except (TypeError, AttributeError, ValueError, KeyError) as e:
						import traceback

						self.fail(f"crashed on {bad!r}: {type(e).__name__}: {e}\n{traceback.format_exc()}")
		finally:
			frappe.set_user("Administrator")

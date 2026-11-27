"""Security review guards (T38): which methods guests can call, and that they are rate limited."""

import ast
import pathlib

from frappe.tests.utils import FrappeTestCase

API = pathlib.Path(__file__).resolve().parent.parent / "api"

GUEST_METHODS = {
	"checkout.extras",
	"checkout.start",
	"public.items",
	"public.quote",
	"public.calendar",
	"payment.stripe_webhook",
}


def _decorators(fn: ast.FunctionDef) -> dict[str, ast.Call | ast.expr]:
	return {
		ast.unparse(d.func if isinstance(d, ast.Call) else d).split(".")[-1]: d for d in fn.decorator_list
	}


def methods():
	for path in sorted(API.glob("*.py")):
		for node in ast.parse(path.read_text()).body:
			if isinstance(node, ast.FunctionDef):
				decs = _decorators(node)
				if "whitelist" in decs:
					yield f"{path.stem}.{node.name}", decs


class TestSecurity(FrappeTestCase):
	def test_only_listed_methods_allow_guests_and_all_are_rate_limited(self):
		guests = set()
		for name, decs in methods():
			call = decs["whitelist"]
			if isinstance(call, ast.Call) and any(k.arg == "allow_guest" for k in call.keywords):
				guests.add(name)
				self.assertIn("rate_limit", decs, f"{name} allows guests without a rate limit")
		self.assertEqual(guests, GUEST_METHODS)

	def test_every_method_names_its_http_verbs_and_changes_need_post(self):
		changing = (
			"cancel",
			"change",
			"sign",
			"finish",
			"start",
			"save",
			"mark_read",
			"install_presets",
			"request",
		)
		for name, decs in methods():
			call = decs["whitelist"]
			listed = None
			if isinstance(call, ast.Call):
				for k in call.keywords:
					if k.arg == "methods":
						listed = ast.literal_eval(k.value)
			self.assertIsNotNone(listed, f"{name} must name its HTTP methods")
			fn = name.split(".")[1]
			if fn.startswith(changing) and not fn.endswith("_preview"):
				self.assertEqual(listed, ["POST"], f"{name} changes data and must be POST only")

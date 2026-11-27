"""Idempotency keys for create calls (T33).

A client sends ``Idempotency-Key: <key>`` (or the ``idempotency_key`` argument). The first successful
response for (user, method, key) is kept for 24 hours; a retry with the same key gets that response back
instead of creating a second record. A retry with the same key but different arguments is rejected, so a
reused key cannot silently return someone else's result.

Kept in the Frappe cache (Redis), which every bench already has. A retry after a Redis flush runs again,
which is the same as a client that sent no key.
"""

import functools
import hashlib
import inspect
import json

import frappe
from frappe import _

TTL = 24 * 60 * 60
HEADER = "Idempotency-Key"
MAX_KEY = 200


class IdempotencyConflict(frappe.ValidationError):
	http_status_code = 409


def _key_from_request(kwargs: dict) -> str | None:
	key = kwargs.pop("idempotency_key", None)
	if not key and getattr(frappe.local, "request", None) is not None:
		key = frappe.get_request_header(HEADER)
	if key is None:
		return None
	key = str(key).strip()
	if not key or len(key) > MAX_KEY:
		frappe.throw(_("Idempotency key must be 1 to {0} characters").format(MAX_KEY))
	return key


def _fingerprint(kwargs: dict) -> str:
	clean = {k: v for k, v in kwargs.items() if k not in ("cmd", "csrf_token")}
	return hashlib.sha256(json.dumps(clean, sort_keys=True, default=str).encode()).hexdigest()


def idempotent(fn):
	"""Decorator for whitelisted create calls. Put it under ``@frappe.whitelist``."""

	params = inspect.signature(fn).parameters

	@functools.wraps(fn)
	def wrapper(*args, **kwargs):
		key = _key_from_request(kwargs)
		kwargs = {k: v for k, v in kwargs.items() if k in params}
		kwargs.update(
			zip(params, args, strict=False)
		)  # positional arguments count towards the fingerprint too
		args = ()
		if not key:
			return fn(*args, **kwargs)
		cache_key = f"rental_idem|{frappe.session.user}|{fn.__module__}.{fn.__name__}|{key}"
		fingerprint = _fingerprint(kwargs)
		cache = frappe.cache
		redis_key = cache.make_key(cache_key)
		raw = cache.get(redis_key)
		cached = json.loads(raw) if raw else None
		if cached:
			if cached["fingerprint"] != fingerprint:
				frappe.throw(_("This idempotency key was used with different arguments"), IdempotencyConflict)
			return cached["response"]
		response = fn(*args, **kwargs)
		# Plain Redis SETEX with JSON: the stored answer is exactly what the client would see.
		cache.setex(
			redis_key, TTL, json.dumps({"fingerprint": fingerprint, "response": response}, default=str)
		)
		return response

	return wrapper

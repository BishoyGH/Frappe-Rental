"""Frappe framework version helpers.

Versions: v15 and v16.
Removal: when v15 support is dropped, IS_V15 can go; IS_V16 stays until v17 is the floor.
"""

import frappe


def frappe_version() -> tuple[int, int, int]:
	"""Return the installed Frappe version as (major, minor, patch)."""
	return _parse(frappe.__version__)


def frappe_major() -> int:
	return frappe_version()[0]


def _parse(version: str) -> tuple[int, int, int]:
	"""Parse '16.61.0', '15.0.0-beta.1' or '16.0.0-dev' into three ints; missing parts are 0."""
	core = version.split("-", 1)[0].split("+", 1)[0]
	parts = [int(p) if p.isdigit() else 0 for p in core.split(".")[:3]]
	parts += [0] * (3 - len(parts))
	return parts[0], parts[1], parts[2]


IS_V15 = frappe_major() == 15
IS_V16 = frappe_major() >= 16

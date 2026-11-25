"""Version compatibility layer for Frappe/ERPNext v15 and v16.

All version-specific behaviour lives in this package. Business code imports from
``frappe_rental.compat`` and never checks versions itself.

Shim docstring convention (required for every shim):
    Versions: which majors differ and how.
    Removal: the condition under which the shim can be deleted.
Prefer feature detection over version numbers; use IS_V15/IS_V16 only as a last resort.
"""

from frappe_rental.compat.frappe import IS_V15, IS_V16, frappe_major, frappe_version

__all__ = ["IS_V15", "IS_V16", "frappe_major", "frappe_version"]

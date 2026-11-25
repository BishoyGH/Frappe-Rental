"""ERPNext-specific shims.

Add helpers here before any task reads ERPNext fields or behaviour that differ between v15 and v16.
"""

import frappe
from frappe.utils import now_datetime


def ensure_setup_complete() -> str:
	"""Run the ERPNext setup wizard on a bare site and return the default company.

	Versions: v15 ships a ``before_tests`` hook that completes setup before ``run-tests``; v16 does not,
	so a fresh bench site has no Company, Warehouse Types, Customer Groups, etc. Detected by feature
	(is there a Company?), not by version number.
	Removal: when v15 support is dropped and v16 gains its own equivalent, or both always run setup.
	"""
	company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
	if company:
		return company

	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	year = now_datetime().year
	setup_complete(
		{
			"currency": "USD",
			"full_name": "Test User",
			"company_name": "Rental Test Co",
			"timezone": "America/New_York",
			"company_abbr": "RTC",
			"industry": "Manufacturing",
			"country": "United States",
			"fy_start_date": f"{year}-01-01",
			"fy_end_date": f"{year}-12-31",
			"language": "english",
			"company_tagline": "Testing",
			"email": "test@example.com",
			"password": "test",
			"chart_of_accounts": "Standard",
		}
	)
	frappe.clear_cache()
	return frappe.db.get_value("Company", {}, "name", order_by="creation asc")

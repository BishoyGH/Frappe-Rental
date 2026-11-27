"""Bench commands for Frappe Rental."""

import click
from frappe.commands import get_site, pass_context


@click.command("rental-demo")
@click.option("--with-bookings", is_flag=True, help="Also create a sample held booking")
@click.option("--basic", is_flag=True, help="Only the Device and Apartment presets")
@pass_context
def rental_demo(context, with_bookings=False, basic=False):
	"""Create demo data for every preset (safe to run twice)."""
	import frappe

	site = get_site(context)
	frappe.init(site=site)
	frappe.connect()
	try:
		from frappe_rental.services.demo import make_demo, make_full_demo

		out = (make_demo if basic else make_full_demo)(with_bookings=with_bookings)
		frappe.db.commit()
		click.echo(f"Demo data ready: {len(out['items'])} items, {len(out['customers'])} customers")
	finally:
		frappe.destroy()


commands = [rental_demo]

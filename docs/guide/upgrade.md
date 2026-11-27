# Upgrade notes

## Upgrading the app

```
cd apps/frappe_rental && git pull
bench --site <site> migrate
bench build --app frappe_rental
```

Migrate is safe to run more than once: patches are idempotent, custom fields and composite indexes are
re-applied without duplicates.

## Moving a site from v15 to v16

1. Upgrade Frappe and ERPNext as their own upgrade guides say, then run `bench --site <site> migrate`.
2. The app needs no data changes between majors; `compat` picks the right ERPNext path at run time.
3. On v16, serial numbers need the Stock Settings switch; the app turns it on when a Serial preset is used.
4. Check that MariaDB, Python and Node match the v16 row of `ci/versions.yml`.

## Changes worth knowing in this release

- Rental Unit status has a new **Turnaround** value (housekeeping tasks).
- Rental Type gains metered usage fields and *Turnaround Task on Return*.
- Customer gains **Consolidate Rental Invoices**; Sales Invoice Item gains booking and billing-row references.
- Rental Contract gains a **Visits** table; Project gains a Rental Booking link.

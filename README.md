# Frappe Rental

Generic rental engine for ERPNext: rent resources and services (apartments, rooms, devices, storage units, photographers, maintenance contracts). See `docs/PLAN.md`.

## Supported versions

Frappe and ERPNext **v15 and v16** from one codebase. Toolchain details: `docs/DEV.md` and `ci/versions.yml`.

## Install

```
# v15 bench
bench get-app https://github.com/BishoyGH/Frappe-Rental
bench --site <site> install-app frappe_rental

# v16 bench: identical commands on a bench created with frappe version-16
```

ERPNext must be installed on the site first. To create dev benches see `docs/DEV.md`.

## Try it locally

You need a working bench with ERPNext (v15 or v16). See `docs/DEV.md` for creating one.

```bash
cd ~/frappe-bench
bench get-app https://github.com/BishoyGH/Frappe-Rental --branch claude/project-thread-dxmafz
bench new-site rental.localhost --admin-password admin --install-app erpnext
bench --site rental.localhost install-app frappe_rental
bench build --app frappe_rental        # builds the staff app (needs Node and yarn)
bench --site rental.localhost execute frappe_rental.tests.e2e_fixtures.setup   # optional sample data
bench start
```

Open http://rental.localhost:8000/rental and log in as Administrator.

- **Bookings** at `/rental/bookings`: list, booking page and the new booking form.
- **Calendar** at `/rental/calendar`: drag across days to book, drag a held booking to move it.
- **Availability** at `/rental/availability`: search free units with their price and book them.
- **Item types, Items, Units and Customers** under Catalog and Setup: define your own rental kinds, such as a boat with its own fields.

The usual desk is still at `/app`.

To run the browser tests against a running site:

```bash
cd apps/frappe_rental/e2e && yarn install && npx playwright install chromium
BASE_URL=http://rental.localhost:8000 yarn test
```

The sample data must be loaded first.

## Licence

GPL-3.0-or-later, see `LICENSE`.

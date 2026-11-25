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

## Licence

GPL-3.0-or-later, see `LICENSE`.

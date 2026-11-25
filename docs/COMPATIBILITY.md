# D8. Supported versions and compatibility (overrides every "Frappe v15" assumption in the other docs)

## Policy
- `frappe_rental` supports **Frappe and ERPNext v15 and v16**, from the first commit. Every PR must pass on both.
- One codebase, one release line. No long-lived per-version forks. Version differences are handled in code (compat layer) and in CI, not by branching the product.
- Supported means: installs, migrates, passes the full test suite and passes the Playwright smoke suite on the **latest stable minor of each major**, with the **oldest supported minor** tested in a nightly job.
- When Frappe publishes the next major (v17), it enters an allowed-failure CI job first, then is promoted after a triage task. When a major reaches end of support, drop it in a minor release with an upgrade note.
- Exact Python, Node, MariaDB and Redis requirements per major are read from the official release notes and recorded once in `ci/versions.yml` (single source of truth for CI, docs and the devcontainer). Do not hard-code them elsewhere. Task T00 verifies and fills this file.

## Branch and release strategy
- `develop` is the only development branch and targets both versions. `main` holds releases.
- App version tags (`v0.x`, `v1.x`) are version-agnostic. `pyproject.toml` declares `frappe>=15,<17` and `erpnext>=15,<17` style bounds (exact form verified in T00).
- Hotfix branches branch from `main`. If a fix is only needed for one version, it still lands on `develop` behind a version gate.
- Frappe Marketplace and Frappe Cloud: publish from tags; the app must install on a bench of either version without edits.

## CI matrix
GitHub Actions matrix, all required checks:

| Axis | Values |
|---|---|
| Frappe/ERPNext | v15 (`version-15`), v16 (`version-16`) |
| Database | MariaDB (required); Postgres allowed-failure until a task enables it |
| Python and Node | taken from `ci/versions.yml` per Frappe version |

Jobs: lint (once), unit and integration tests (matrix), Playwright smoke (matrix), frontend build (matrix), install-and-migrate-from-previous-release (matrix, from T60 onward). Nightly: oldest supported minors, and the next major as allowed-failure. Coverage is reported per matrix leg; service-layer coverage target applies to both.

## Compatibility rules (for Claude Code)
1. **Stable APIs first.** Use only documented Frappe public APIs (`frappe.get_doc`, `frappe.db.get_value`, query builder, whitelisted methods, hooks). Avoid private helpers (leading underscore), internal modules and anything marked deprecated.
2. **Prefer queries through the query builder** (`frappe.qb`) or `frappe.get_all`/`get_list`; never raw SQL unless unavoidable and then ANSI-portable with parameters.
3. **No monkey patching or core overrides.** Extend through hooks, custom fields (fixtures) and links, so core changes cannot silently break us.
4. **One compat layer.** All version-specific behaviour lives in `frappe_rental/compat/` (modules such as `frappe.py`, `erpnext.py`, `ui.py`). Business code imports from `compat`, never checks versions itself. Each shim has a docstring naming the versions it covers and a removal condition.
5. **Version gates are explicit.** Use `compat.IS_V16` / `compat.frappe_version()` helpers, and prefer **feature detection** (`hasattr`, try/except ImportError at import time inside `compat`) over version numbers.
6. **ERPNext doctype fields.** Accessing ERPNext fields that differ by version goes through `compat.erpnext` helpers (for example account fields, asset and subscription fields). Never read a field that exists only in one version without a guard.
7. **DocType JSON.** Keep standard field types and properties common to both versions. Any property introduced in v16 is added through a patch or a conditional fixture, not hard-coded in shared JSON.
8. **Hooks.** `hooks.py` must load on both versions; optional hooks are appended conditionally via compat.
9. **Dependencies.** Python dependencies must resolve on every supported Python version. No dependency that conflicts with Frappe's own pinned versions.
10. **Migrations.** Patches are idempotent and tested by migrating from the previous release on both versions.
11. **Deprecation hygiene.** CI runs tests with deprecation warnings visible; new deprecation warnings from our code fail the build.
12. **Tests prove compatibility.** Every compat shim has a test that runs on both versions; new features need no version-specific tests unless they use a shim.

## Frontend (Vue and frappe-ui)
- The staff app and customer flow are built with **Vue 3 and `frappe-ui`**, served by the app itself, so the frontend is bundled by us and does not depend on the Frappe desk's own JS version.
- Pin `frappe-ui` and Vue in `frontend/package.json` to one version that works on both Frappe majors. Frappe version differences reach the frontend only through our whitelisted API (`frappe_rental.api.*`), which is stable and versioned, not through desk globals.
- Avoid depending on desk JS objects (`frappe.ui`, `cur_frm`) from the SPA. Desk-side scripts (Item type builder forms, setup screens) use only documented client APIs and are covered by the Playwright smoke suite on both versions.
- Node version for building comes from `ci/versions.yml`; the built assets are committed or built in release CI, so end users never need Node.
- Session, CSRF and login use the standard `/api/method` and cookie session mechanisms, which are identical across versions.

## Python and Node differences
- Write code for the **lowest supported Python** and test on all supported ones (CI matrix). Use no syntax or stdlib features newer than the lowest.
- Type hints and `ruff` target the lowest Python.
- Node tooling versions are pinned per matrix leg through `ci/versions.yml` and an `.nvmrc` that tracks the highest supported.

## Documentation and support
- README states supported versions and the install command for each. `docs/DEV.md` shows how to create a bench for either version (and both side by side via two benches).
- Issue template asks for Frappe and ERPNext versions.
- Changelog notes any version-specific behaviour.

## Task impact
New early tasks: **T00A** (verify requirements, create `ci/versions.yml`), **T00B** (dual-version dev environment and docs), **T00C** (compat layer and its tests). T01, T02, T03 and later tasks that touch ERPNext (T16, T25, T27, T36, T56, T60) are amended in `TASKS.md`.

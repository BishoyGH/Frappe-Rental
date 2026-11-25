# Frappe Rental: instructions for Claude Code

App `frappe_rental` extending ERPNext, supporting **Frappe and ERPNext v15 and v16** with one codebase. Generic rental engine: anything can be rented (resources and services).

## Source of truth (read before any task)
1. `docs/COMPATIBILITY.md` (v15 and v16 rules) overrides every "Frappe v15" mention elsewhere.
2. `docs/FINAL_DECISIONS.md`, `docs/INVOICING.md`, `docs/CONTRACTS.md`, `docs/DECISIONS.md` override `docs/PLAN.md` where they differ.
3. `docs/PLAN.md` for DocTypes, workflows, ERPNext map, API, layout.
4. `docs/TASKS.md` is the ordered backlog. Work one task at a time, in order, unless a task says otherwise.

## How to work a task
- Pick the first unchecked task whose dependencies are done. Do only that task.
- Branch `task/<id>-<slug>` from `develop`. One PR per task, small and reviewable. Title `T<id>: <summary>`.
- Tick the task in `docs/TASKS.md` in the same PR and note anything deferred.
- Definition of done: acceptance criteria met, tests written and passing **on both v15 and v16**, `ruff` and pre-commit clean, CI matrix green, docs updated, no TODOs left without a linked task.
- If the plan is ambiguous or a decision is missing, stop and ask; record the answer in `docs/DECISIONS.md`.

## Version compatibility rules (v15 and v16)
- Code must work unchanged on both majors. Do not write anything that only one supports.
- Use only documented public Frappe and ERPNext APIs. No private helpers, no monkey patching, no core overrides.
- All version-specific code lives in `frappe_rental/compat/`. Business code imports from `compat` and never checks versions itself. Prefer feature detection over version numbers. Every shim has a docstring (versions covered, removal condition) and a test.
- Versions of Python, Node, MariaDB and Redis come only from `ci/versions.yml`. Do not hard-code them in other files.
- Reproduce and test failures on both versions before fixing. If a fix is needed on one version only, gate it in `compat` and keep the other path covered.
- The frontend is bundled with the app (Vue 3 + `frappe-ui`) and talks only to `frappe_rental.api.*`. Do not depend on desk globals such as `cur_frm` from the SPA.
- New deprecation warnings from our code fail CI.
- When a task touches ERPNext fields or behaviour that differ between versions, add or extend a compat helper first.

## Engineering rules
- Business logic lives in `frappe_rental/services/` as plain, unit-testable Python. DocType controllers stay thin. API methods only validate, permission-check and call services.
- Never override ERPNext core controllers. Use hooks, custom fields (fixtures) and links.
- All money uses Frappe currency fields and `flt` with precision; never floats in comparisons. Datetimes stored UTC, shown in the Location timezone.
- Every whitelisted method checks permissions (`frappe.has_permission`) and validates input. No `ignore_permissions=True` without a comment and a test.
- Every user-facing string wrapped in `_()`. No hard-coded company, account or item names; read from Rental Settings.
- Anything with side effects on other documents is idempotent (safe to run twice) and runs in a transaction. Concurrency-sensitive code (availability, billing) has a test.
- Migrations: patches are idempotent; schema changes via DocType JSON only.
- Tests: `FrappeTestCase`, fixtures built in code, no reliance on demo data. Target 85% coverage on `services/`.
- Frontend follows the mockups (Frappe UI look). No custom design system.
- Commits: small, imperative. Never commit secrets.

## Commands
```
bench get-app frappe_rental <path>; bench --site rental.localhost install-app frappe_rental
bench --site rental.localhost run-tests --app frappe_rental
ruff check . && ruff format --check .
cd frontend && yarn && yarn dev | yarn build
```
Create one bench per supported major (see `docs/DEV.md`, task T00B) and run tests on both.

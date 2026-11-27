# Releasing (T60)

1. All tasks ticked in `docs/TASKS.md`, CI green on v15 and v16, `python scripts/extract_messages.py --check ar` clean.
2. Set `__version__` in `frappe_rental/__init__.py` and add a heading for it in `CHANGELOG.md` (`tests/test_release.py` checks both).
3. Upgrade check: on a bench with the previous tag installed, `git checkout <new>`, `bench --site <site> migrate`, then run the test suite. Every migrate re-runs `install.after_install`, which is idempotent and covered by a test. There are no data patches: schema changes are DocType JSON only.
4. Packaging: `cd frontend && yarn install --frozen-lockfile && yarn build` produces `public/frontend` and `www/rental.html` (both git-ignored build output), so Marketplace and Frappe Cloud builds must run `bench build --app frappe_rental` or the frontend build before packaging. Check `pyproject.toml` bounds against `ci/versions.yml`.
5. Tag `v1.0.0` on main (`git tag -a v1.0.0 -m "v1.0.0"` and push the tag). Earlier tags `v0.1.0` (phase 3) and `v0.2.0` (phase 4) are only added if wanted for history.
6. Next major: keep the next-major CI job as allowed-to-fail until its tests pass, then promote it to the matrix in `ci/versions.yml`.

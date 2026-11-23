# Cargo verification

Run commands inside a compatible Docker-based Bench. From `apps/cargo_management`, source and unit checks need no site:

```bash
python -B scripts/check_source.py
python -B -m unittest cargo_management.tests.test_release_policy cargo_management.tests.test_outbound_safety cargo_management.tests.test_portability_metadata cargo_management.tests.test_remediation
node --test cargo_management/tests/test_client_compatibility.cjs cargo_management/tests/test_booking_order_calculations.cjs
```

Client calculations read the installed sibling Frappe dispatcher. Expected results are independent of Git HEAD and work in source archives.

## Disposable native tests

Use a separate Bench, database, Redis and credentials. Mute email, disable scheduler execution, leave crypto off and deny external egress after dependency bootstrap. Never use an existing business site or another site's database/records.

Create a fresh `cargo-publication-RUN.localhost` site with database `cargo_publication_RUN`. RUN is a newly generated 16-character lowercase hexadecimal identifier. Set `cargo_publication_test_run` to RUN, `mute_emails` to true, `cargo_crypto_enabled` to false and `allow_tests` to true only on that site. All writers validate the exact site/database/marker pair.

Install ERPNext and Cargo normally, migrate twice and build assets. First prove installation created no business data:

```bash
bench --site TEST_SITE execute cargo_management.tests.test_clean_install.assert_metadata_only
```

Then explicitly create synthetic test-only masters and run native tests:

```bash
bench --site TEST_SITE execute cargo_management.tests.isolated_fixtures.prepare
bench --site TEST_SITE run-tests --app cargo_management
```

The generated ownership registry lives inside that disposable site's private directory. Fixtures use example.invalid identities and illustrative prices; no original records, passwords or private evidence are inputs. Installation hooks never invoke fixtures. Each native regression rolls back its created records and verifies their absence.

Upgrade tests cover accepted field orders, foreign fields, classifier transitions and conflicts. Separate qualification installs the captured migrated v16 predecessor into another disposable database, creates synthetic records, updates to this source and migrates twice with preservation checks.

## Browser and packaging

Install development tooling with `yarn install --frozen-lockfile` and `yarn playwright install chromium`. Start disposable web/realtime services. Supply `CARGO_TEST_URL`, `CARGO_TEST_SITE`, `CARGO_TEST_RUN` and `CARGO_TEST_ADMIN_PASSWORD` through private environment inputs, then run `yarn test:browser`. The runner validates its destination before creating fixtures. PDFs use the native renderer; QR output is independently decoded.

Financial tests submit/cancel only synthetic documents. Concurrency tests use independent database connections and test-owned drafts. Keep results, screenshots, credentials and packages outside Git.

With the development build frontend installed, run `python -m build --sdist --wheel --outdir /PRIVATE/ARTIFACTS`. Inspect both artifacts for all required metadata, templates and assets and absence of private/site/build material. Finally qualify normal `bench get-app` installation from the exact committed source.

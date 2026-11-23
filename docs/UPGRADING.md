# Upgrading Cargo Management v16

Run Bench commands inside the intended Docker environment. Take and verify a recoverable backup of that site's database, files and configuration. Record Cargo/framework commits and rehearse on an authorized isolated copy.

Fetch and review `version-16`. Preserve local source changes and use a normal fast-forward update where possible. Do not reset work, force-install Cargo or overwrite conflicting customization.

After updating source, from the Bench directory:

```bash
bench setup requirements --python
bench --site YOUR_SITE migrate
bench build --production --apps cargo_management
bench pip check
```

Reconciliation adds owned metadata idempotently. Conflicting field types and unrecognized field orders fail for review. Accepted legacy orders preserve foreign custom fields. Location's Cargo classifier transitions from Data to Select only when nonblank values are valid. Existing blanks remain optional; new Locations require classification.

Native synchronization widens Expenses amounts to Currency precision. Previously truncated values are not reconstructed. Version-0 contracts, financial references and Cross-Stuff history remain preserved. Migration imports no catalogs, prices, counters or transactions.

Resolve conflicts against the target site's customizations before continuing. Recovery uses its verified backup and documented recovery procedure; a migration error does not authorize dropping tables or importing another site's data.

Qualification covers the migrated pre-publication v16 source to this branch, repeated migration and representative legacy metadata states/conflicts using synthetic data. It does not establish a live Frappe v15-to-v16 upgrade. Original v15 `main` has incomplete dependencies and incorrect installation-hook paths and is not a qualified fresh-install baseline on v16.

Verify navigation, Company/role permissions, reports, printing and approved representative workflows after migration. Configure operating catalogs using [CONFIGURATION.md](CONFIGURATION.md).

# Cargo Management for Frappe / ERPNext v16

Cargo Management covers Booking Orders, Sales Orders, Freight Orders, Road/Rail/Yard/Cross-Stuff operations, containers and wagons, expenses and invoicing. It contains 31 original DocTypes, two Cross-Stuff financial-history models, 16 reports and two invoice print formats.

## Installation

Use an existing Docker-based Frappe/ERPNext v16 Bench with ERPNext installed on the intended site. Qualification baseline: Frappe **16.55.1**, ERPNext **16.53.0**, Python **3.14.10**, Node **24.22.2**, Yarn **1.22.22**, Bench **5.31.1**, MariaDB **11.8.9**, Redis **7.4.12**. Version constraints do not certify every v16 release.

Inside the Bench container, from its Bench directory:

```bash
bench get-app --branch version-16 https://github.com/DeliveryDevs-ERP/Cargo-Management.git
bench --site YOUR_SITE install-app cargo_management
bench --site YOUR_SITE migrate
bench build --production --apps cargo_management
bench pip check
```

Bench installs the declared Python dependencies. Frappe and ERPNext are managed by Bench. Do not use an initial-environment installer or force-install onto an existing business site.

Installation creates schema, Cargo roles, integration fields and application-owned UI metadata. It creates **no Companies, parties, Items, operating catalogs, tariffs, sequences, transactions or demonstration records**. No development database, separate source archive or manual file copying is required.

## Configuration

Follow [Company configuration](docs/CONFIGURATION.md) for native ERPNext Company/chart/fiscal year, parties, service Items/UOMs, accounts, cost centers and Cargo catalogs. Required transport modes are `Road (Truck)` with mode `Road`, and `Rail (Train)` with mode `Rail`. Bind service sequences to records created in the target site.

Configure classified Locations, container/wagon capacities, services, sequences, expense Item/Supplier bindings and approved tariffs before operational use. Test prices are synthetic examples. Existing blank-Company legacy catalogs remain supported; a Company-specific catalog is exclusive and must be complete. Missing or ambiguous configuration fails explicitly.

Cargo Operator normally combines with native Sales User, Accounts User and Stock User roles. Cargo Manager complements appropriate native manager roles. Apply Company User Permissions. Cargo preserves native accounting authority.

Open Cargo Management through the app switcher or `/desk/cargo-management`. Invoice formats: **Sales Invoice PF Midway** and **Sales invoice pf with qr**. Use a Frappe-supported PDF renderer. The tested Chromium executable is `/usr/bin/chromium-headless-shell`; select an installed executable through native Bench `chromium_path` configuration when required. Configure the native site hostname for QR links. QR output contains an authenticated invoice URL without access tokens.

## Upgrades and verification

See [upgrade instructions](docs/UPGRADING.md) and [repeatable tests](docs/TESTING.md). Approved versioned billing, deterministic rail tariffs, expense precision, Company isolation, allocations and Cross-Stuff history protections are retained. Existing version-0 contracts remain unchanged; new records use version 1. Migration does not reprice historical transactions or infer missing weights.

Commercial tariff authority, partially received wagon pricing, bag-weight/fallback semantics and currency scope require business confirmation. Successful source installation is distinct from production/business certification.

## Optional integrations

Crypto is disabled by default and its scheduled job is stopped. Optional dependencies can be installed with `bench pip install -e 'apps/cargo_management[crypto]'`. Installation does not enable execution. Live opt-in requires private `cargo_crypto_database_url` and `cargo_crypto_api_key` settings and separate authorization. Keep secrets outside source and fixtures; tests mock provider, PostgreSQL and email calls.

Sites named `erp16.local` retain the development HTTP/job outbound protections. Other site names configure their own integrations, email and scheduler policies. This application policy is not a network firewall. Financial QA guards are not installed. Framework/vendor dependency risks need deployment-specific review; Cargo does not patch framework source or certify production security or Marketplace readiness.

## Licence

MIT. Preserve original author/publisher attribution in project metadata and `license.txt`.

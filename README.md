# ERPNext PWAs

> **🇸🇦 ZATCA Phase 2 (Fatoora) e-invoicing for ERPNext: proof of concept.** Sales Invoices are signed in Python and
> cleared or reported with ZATCA's sandbox, with retries, an outbox and readable rejections.
> **Sandbox-tested only.** [See the demo and limitations ↓](#zatca-phase-2-e-invoicing-saudi-arabia) ·
> [technical write-up](docs/zatca/README.md)

Four mobile-first apps (sales, HR, accounts and admin) built on top of ERPNext and Frappe HR, plus the launcher everyone
lands on after login. ERPNext still owns the data and does all the accounting. The apps give each team a simpler front door
than desk: fewer fields, the next step suggested, the gaps behind "the numbers look wrong" flagged and fixable in one
click, and each screen made for a phone as well as a PC.

Made for Southern African small businesses: two currencies on every screen (USD/ZWG out of the box), PAYE from
published tax bands, and the central bank's daily rate. The screenshots below come from a demo site with
**fictional data** (`erp_overrides/demo.py`).

![Launcher](docs/screenshots/launcher/home-desktop.png)

| App | Address | For | Docs |
|---|---|---|---|
| Launcher | `/launcher` | Everyone: one tile per app their roles open, plus Desk | [sysadmin-pwa.md](docs/sysadmin-pwa.md#landing-page-launcher) |
| Sales | `/sales` | Lead → quotation → order → invoice, and buying for an order | [sales-pwa.md](docs/sales-pwa.md) |
| HR | `/hrms-admin` | Leave, payroll, claims, people and bi-weekly reviews | [hr-admin-pwa.md](docs/hr-admin-pwa.md) |
| Accounts | `/accounts` | Bank reconciliation, money owed, payments, petty cash, exchange rates | [accounts-pwa.md](docs/accounts-pwa.md) |
| Admin | `/sys-admin` | Users and roles, why someone can't open something, item prices and imports | [sysadmin-pwa.md](docs/sysadmin-pwa.md) |

## ZATCA Phase 2 e-invoicing (Saudi Arabia)

> **Status: proof of concept, sandbox only.** It runs end to end against ZATCA's public **developer-portal sandbox**. It
> has not been run in ZATCA's simulation or production environments, and it is not a ZATCA-certified solution.

`erp_overrides/zatca/` connects ERPNext to ZATCA's FATOORA platform:
- Standard (B2B) invoices are sent for **clearance**.
- Simplified (B2C) invoices are sent for **reporting**.
- Credit and debit notes are covered too.

The UBL 2.1 XML, invoice hash, XAdES signature and QR code are built in Python (`lxml` + `cryptography`), written directly
from ZATCA's published specifications. There's no Java SDK and no shelling out. The module is off unless it's switched on
for a company, so the rest of this repo is unaffected.

### Demo

Fictional demo data on ERPNext v16, sent live to the ZATCA sandbox.

**1. Submit a B2B invoice: ZATCA clears it and returns its QR. Then a B2C invoice is reported.**

| Desktop | Phone |
|---|---|
| ![Clearance and reporting, desktop](docs/screenshots/zatca/clearance-reporting-desktop.gif) | <img src="docs/screenshots/zatca/clearance-reporting-phone.gif" width="260" alt="Clearance and reporting, phone"> |

**2. ZATCA rejects an invoice (buyer VAT number has 14 digits, rule BR-KSA-44). Sales fixes the customer, Accounts sends it again, and it's cleared.**

| Desktop | Phone |
|---|---|
| ![Reject and retry, desktop](docs/screenshots/zatca/reject-retry-desktop.gif) | <img src="docs/screenshots/zatca/reject-retry-phone.gif" width="260" alt="Reject and retry, phone"> |

### What it does

- **Onboarding and renewal:**
  - New key and CSR (secp256k1).
  - Compliance CSID, then the six compliance checks (standard and simplified invoice, credit note and debit note), all
    `PASS`.
  - Production CSID.
  - **Renew CSID** button.
  - Credentials are stored encrypted in the site database, never in git.
- **Clearance and reporting:**
  - Real Sales Invoices come back **CLEARED** / **REPORTED** with no warnings, including credit notes and a 0% line with
    an exemption code.
  - Cleared invoices keep ZATCA's stamped XML and QR.
- **Invoice chain:**
  - The counter (ICV) and the previous-invoice hash (PIH) are handed out under a row lock inside the submit transaction.
  - A rejected document stays in the chain, as ZATCA requires.
  - Retry signs a new document; it never edits the old one.
- **Outbox:**
  - Every submitted invoice has a durable submission record.
  - A sweeper sends anything the background job missed, and retries failures with backoff (1, 5, 15 and 60 minutes, then
    hourly, up to 10 attempts).
  - A row lock prevents two sends of the same document.
  - An hourly check flags B2C invoices close to ZATCA's 24-hour reporting limit.
- **Readable errors:**
  - ZATCA's rejections are shown in plain words on the invoice.
  - Missing B2B address fields are caught before signing.
  - Cancelling an invoice ZATCA has accepted is blocked: a credit note is required instead.
- **Tests:**
  - 20 unit tests, including ZATCA's own worked QR example and reply bodies from the API reference.
  - 7 outbox integration tests with ZATCA mocked.
  - Tested on Frappe 16.51.1 and ERPNext 16.50.0.

### Limitations

- **Sandbox only:**
  - The developer portal gives everyone the same certificate and doesn't detect duplicate submissions. So signing with
    a key matched to its certificate, and the duplicate replies (HTTP 208 / 409), still need testing in the simulation
    environment.
  - The duplicate replies are handled in code and covered by unit tests.
- **Scope:**
  - One company and one EGS unit.
  - SAR invoices only.
  - VAT categories S (standard) and Z (zero-rated); E (exempt) and O (out of scope) aren't mapped.
  - No document-level allowance or charge lines in the XML; discounts are carried in each line's net price.
- **Not built yet:**
  - A bilingual Arabic/English invoice print format. The QR is shown on the form.
  - Batched reporting within the 24 hours.
  - Multi-branch devices.
- **Production needs:** the client's VAT number and CR, an OTP from their Fatoora portal, onboarding in simulation then
  production, and their invoice templates.

The design, ZATCA's reply codes, what the sandbox taught us, setup and tests are in **[docs/zatca/README.md](docs/zatca/README.md)**.
[ERPGulf/zatca_erpgulf](https://github.com/ERPGulf/zatca_erpgulf) (MIT) is prior art. None of its code is used here.

## Screenshots

### Sales

| Desktop | Phone |
|---|---|
| ![Sales home](docs/screenshots/sales/home-desktop.png) | <img src="docs/screenshots/sales/home-phone.png" width="260"> |
| ![Quotation](docs/screenshots/sales/quotation-desktop.png) | <img src="docs/screenshots/sales/quotation-phone.png" width="260"> |
| ![Sales reports](docs/screenshots/sales/reports-desktop.png) | <img src="docs/screenshots/sales/reports-phone.png" width="260"> |

### HR

| Desktop | Phone |
|---|---|
| ![HR home](docs/screenshots/hr/home-desktop.png) | <img src="docs/screenshots/hr/home-phone.png" width="260"> |
| ![Payroll run](docs/screenshots/hr/payroll-desktop.png) | <img src="docs/screenshots/hr/payroll-phone.png" width="260"> |
| ![Who's off](docs/screenshots/hr/whos-off-desktop.png) | <img src="docs/screenshots/hr/whos-off-phone.png" width="260"> |

### Accounts

| Desktop | Phone |
|---|---|
| ![Accounts home](docs/screenshots/accounts/home-desktop.png) | <img src="docs/screenshots/accounts/home-phone.png" width="260"> |
| ![Bank reconciliation](docs/screenshots/accounts/bank-desktop.png) | <img src="docs/screenshots/accounts/bank-phone.png" width="260"> |

### Admin

| Desktop | Phone |
|---|---|
| ![Users](docs/screenshots/admin/users-desktop.png) | <img src="docs/screenshots/admin/users-phone.png" width="260"> |
| ![Items and prices](docs/screenshots/admin/prices-desktop.png) | <img src="docs/screenshots/admin/prices-phone.png" width="260"> |

More screens are in each app's doc, and every capture is in [`docs/screenshots/`](docs/screenshots).

## How it's built

- **Frontend:** Vue 3, [frappe-ui](https://github.com/frappe/frappe-ui), Tailwind and Vite, with `vite-plugin-pwa`, so each app
  installs to a phone's home screen. There's one `frontend/` folder with four Vite configs (`vite.config.js`,
  `vite.hr.config.js`, `vite.accounts.config.js`, `vite.sysadmin.config.js`) that share components.
- **Backend:** whitelisted methods in `erp_overrides/api/` (`sales.py`, `hr.py`, `pay_setup.py`, `reviews.py`, `accounts.py`,
  `sysadmin.py`, …). Every method checks the caller's roles and goes through ERPNext's own documents, so desk's validation,
  permissions and version history still apply.
- **Server-side rules:** document hooks in `hooks.py`. These include a three-way match before a supplier is paid
  (`three_way.py`), light-touch stock for hardware bought to order (`stock_light.py`), quotation print guards, and a payslip
  format with leave balances (`payslip.py`).
- **Custom doctypes:** bi-weekly reviews (Review, Review Form, Review Schedule), petty cash boxes, the accounts app settings,
  and public tenders for Zimbabwe and Zambia, with the feeds left as stubs (see below).
- **Tests:** `erp_overrides/tests/` has a module per API (`run-tests --app erp_overrides`).

Requires Frappe, ERPNext and Frappe HR **v16**, Python 3.14 and Node 20+.

## Try it

```bash
bench get-app https://github.com/Zawala/erpnext_overrides.git
bench new-site demo.localhost --install-app erpnext --install-app hrms --install-app erp_overrides
bench --site demo.localhost execute erp_overrides.demo.seed     # fictional company, staff and transactions
bench build --app erp_overrides
bench start
```

Open http://demo.localhost:8000/launcher and log in as `Administrator` (the password you gave `new-site`), or as
any demo user (`grace@example.com`, `ruth@example.com`, `daniel@example.com`, …) with the password `demo1234`.

To try the ZATCA proof of concept on the same site, sending to ZATCA's public sandbox:

```bash
bench --site demo.localhost execute erp_overrides.zatca.demo.seed        # fictional Saudi company, 15% VAT, B2B and B2C customers
bench --site demo.localhost execute erp_overrides.zatca.onboarding.run   # CSR → compliance checks → production CSID
bench --site demo.localhost execute erp_overrides.zatca.demo.invoices    # a B2B invoice, a B2C invoice and a credit note
```

Then log in as `daniel@example.com` and open **ZATCA Settings** and **ZATCA Submission**, or any of the new Sales Invoices.

For frontend development, run `cd frontend && yarn dev` (sales), `yarn dev:hr`, `yarn dev:accounts` or `yarn dev:sysadmin`.
Each one proxies API calls to the bench.

## Tenders and exchange rates across SADC

The app is wired for two daily feeds: new **public tenders** from national e-procurement portals, shown on a Tenders page and
emailed as a digest, and the **central bank's exchange rate** written into ERPNext every weekday. The fetching code is left
out, and `erp_overrides/scrapers.py` has stubs with the same entry points. [docs/sadc-data-feeds.md](docs/sadc-data-feeds.md)
covers how the same design extends to SADC's 16 member states and how to plug in a source.

## License

MIT

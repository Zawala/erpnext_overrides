# ZATCA Phase 2 (Fatoora) e-invoicing: proof of concept

> **Sandbox-tested, not production-certified.** Everything here has been run against ZATCA's public
> developer-portal sandbox only. Production needs a real taxpayer's VAT number, an OTP from the
> Fatoora portal, onboarding in the simulation and core environments, and the client's own invoice templates.

This module signs ERPNext Sales Invoices and sends them to ZATCA. Standard (B2B) invoices go
through **clearance** and simplified (B2C) ones through **reporting**. The UBL XML, invoice hash,
XAdES signature and QR code are built in Python (`lxml` + `cryptography`) straight from ZATCA's
published specifications, so there's no Java SDK and no shelling out to it.

## What's been proven

Results from live calls to `https://gw-fatoora.zatca.gov.sa/e-invoicing/developer-portal`:

| Step | Result |
|---|---|
| CSR (secp256k1) → compliance CSID, OTP `123345` | Issued |
| Compliance checks: standard and simplified invoice, credit note and debit note (6 documents) | All `PASS` |
| Production CSID | Issued |
| Clearance: standard invoice, standard credit note | `CLEARED`, no warnings, stamped XML returned |
| Reporting: simplified invoice, simplified credit note (incl. a 0% line with exemption code) | `REPORTED`, no warnings |
| Tampered invoice (one item name changed after signing) | Rejected: `invalid-invoice-hash` / `invoiceHash_QRCODE_INVALID` |
| CSID renewal (`PATCH /production/csids`, new key and CSR, OTP `123345`) | New production CSID issued (HTTP 200) |

### Through ERPNext (Frappe 16.51.1, on a local site with the demo data below)

| Step | Result |
|---|---|
| `bench migrate` | Clean: both doctypes, the custom fields and the patch applied |
| Onboarding from ZATCA Settings (`onboarding.run`) | 6 compliance checks `PASS`, production CSID stored, valid until 2029-01-09 |
| B2B Sales Invoice (2 lines, 15% VAT, 4,139.97 SAR) | **Cleared**; ZATCA's stamped XML and QR stored |
| B2C Sales Invoice (401.35 SAR) and its credit note | **Reported** both, with our QR (tags 1–9) |
| Invoice chain | ICV 1, 2, 3…; each PIH equals the previous hash; the first is the spec's seed |
| B2B customer with a malformed VAT number | **Rejected**: `BR-KSA-44: … must contain 15 digits. The first digit and the last digit is "3"` |
| Fix the customer, click *Send to ZATCA again* | Re-signed as a new document (ICV 5, PIH = the rejected hash) and **Cleared**; the old one is *Superseded* |
| Next invoice after the rejection | Reported, still chained |
| B2B customer without an address | Submit blocked before signing, with the missing fields listed; ICV not used up |
| Cancel a cleared invoice | Blocked: "Issue a credit note instead" |
| Renew CSID (`onboarding.renew`) | New CSID; chain kept; the next invoice is reported |
| Background job (`bench worker`) | Invoice *Pending* after submit, *Cleared* once the worker ran |
| Two senders at once (separate processes) | The second `send` returns *Busy* while the first holds the row; ZATCA is called once |
| Sweeper, live | A submission that failed and was due a retry was **Reported** on attempt 2; a *Pending* one its job never sent was picked up |
| Outbox integration tests (ZATCA mocked) | 7/7 pass: missed job, backoff then success, network error, giving up after 10 attempts, no resend once settled, lock skip, overdue flag |
| Zimbabwe demo company | No ZATCA activity |

**Not checked in a browser yet:** the Desk buttons, status indicator and QR display
(`zatca_sales_invoice.js`, the ZATCA Settings buttons).

## How it works

```
Sales Invoice submit
  └─ before_submit  check → next ICV + previous hash (row lock) → UBL XML → hash + XAdES sign → QR
                    → ZATCA Submission (Pending), all inside the submit transaction
  └─ on_submit      queue send() to run after commit
       send()       clearance (standard) or reporting (simplified) → Cleared / Reported /
                    Accepted with warnings / Rejected / Failed, written to the submission and invoice
```

- **Invoice chain.** Each document carries its counter (ICV) and the previous document's hash
  (PIH). Both are handed out under a `SELECT … FOR UPDATE` lock on ZATCA Settings, inside the
  submit transaction, so a failed submit doesn't leave a gap.
- **Retry.** A *Failed* send (network, auth, 5xx) resends the same signed XML. A *Rejected*
  document is final: once the cause is fixed, retry signs a **new** document with a new ICV and UUID.
  The rejected one stays in the chain, because ZATCA records rejected hashes too, and is marked *Superseded*.
- **Outbox.** The *ZATCA Submission* row is written in the same transaction as the invoice, so every
  submitted invoice has one and nothing is lost if Redis or a worker is down. The queued job is only the
  fast path. A **sweeper** (`submit.sweep`, every 5 minutes) sends:
  - *Pending* submissions older than 3 minutes, which their job never sent, and
  - *Failed* ones that are due a retry, on a backoff of 1, 5, 15 and 60 minutes, then hourly, up to 10 attempts.

  After that the submission waits for a person (*Send to ZATCA again*). `send()` takes a row lock
  (`FOR UPDATE SKIP LOCKED`), so the job, the sweeper and the button never send the same document at once,
  and a settled submission is never sent again. An **hourly check** (`submit.check_overdue`) writes an
  Error Log entry listing simplified invoices still not reported 20 hours after issue, because ZATCA's limit
  is 24 hours. ZATCA Settings shows the outbox: how many are pending, failed, given up, rejected and overdue.
- **Cancelling** an invoice ZATCA has accepted is blocked; issue a credit note instead.
- **Renewal.** *Renew CSID* in ZATCA Settings makes a new key and CSR and calls `PATCH /production/csids`,
  authenticated with the current production CSID. If ZATCA answers 428 `NOT_COMPLIANT`, it hands back a
  compliance CSID, so the six compliance checks run again before the new production CSID is fetched.
  Unlike onboarding, renewal keeps the invoice chain. The certificate's expiry date is shown in the settings.
- **Standard or simplified:** a customer of type Company with a VAT number (`tax_id`) gets a standard
  invoice; everyone else gets a simplified one. Returns become credit notes (381) and debit notes are 383.

### How ZATCA's replies are recorded

From ZATCA's sandbox API reference (Sandbox Release 2.1.0); handled in `submit.send()` and `client.py`:

| HTTP | Meaning | Recorded as |
|---|---|---|
| 200 | Cleared / reported | *Cleared* / *Reported* |
| 202 | Accepted with warnings | *Accepted with warnings*, warnings stored |
| 208 | Clearance: this hash was already submitted (body still has `clearedInvoice`) | *Cleared*, with a note |
| 303 | Clearance is switched off at ZATCA | Sent again through reporting; recorded from that reply, with a note |
| 400 | Rejected (`errorMessages`, or a top-level `errors` list on the CSID endpoints) | *Rejected*; ZATCA's messages shown |
| 401 | Wrong or missing credentials | *Failed*: "renew the CSID" |
| 406 | Missing or unsupported `Accept-Version` | *Failed* |
| 409 | Reporting: already reported earlier | *Reported*, with a note |
| 428 | Renewal: `NOT_COMPLIANT` | Compliance checks run, then the production CSID |
| 5xx, network | ZATCA or the connection failed | *Failed*; retry resends the same XML |

The developer-portal sandbox doesn't detect duplicates (a resend gets 200 again), so 208 and 409 are
covered by unit tests built from the API reference's example bodies, not by live calls.

## Files

### Pure modules: no Frappe import, testable with plain pytest

| File | Purpose |
|---|---|
| `erp_overrides/zatca/ubl.py` | Invoice dict → UBL 2.1 XML. Totals are worked out from the lines so they always add up the way the validator checks |
| `erp_overrides/zatca/crypto.py` | secp256k1 key, CSR with ZATCA's subject and SAN fields, invoice hash, ECDSA signature, XAdES block |
| `erp_overrides/zatca/qr.py` | QR code: base64 TLV, tags 1–9 |
| `erp_overrides/zatca/document.py` | One call: dict → signed XML with the QR written in |
| `erp_overrides/zatca/client.py` | FATOORA API client: compliance, production CSID, renewal, clearance, reporting; reads every error shape into readable lines |
| `erp_overrides/zatca/tests/test_pure.py` | 20 unit tests: the Guideline's QR example, rounding, type codes, hash and signature, SignedProperties digest, CSR fields, API reply parsing |

### Frappe side

| File | Purpose |
|---|---|
| `erp_overrides/zatca/mapping.py` | Sales Invoice → dict; `check()` lists what would make ZATCA reject it, in plain words |
| `erp_overrides/zatca/submit.py` | Doc events, the chain, `send` (row-locked), whitelisted `retry`, `qr_svg` and `backlog`; the outbox `sweep` and `check_overdue` |
| `erp_overrides/tests/test_zatca.py` | Outbox integration tests with a fake ZATCA client: `bench --site <site> run-tests --module erp_overrides.tests.test_zatca` |
| `erp_overrides/zatca/demo.py` | Fictional Saudi demo: `seed` (company, VAT 15%, customers, settings) and `invoices` (B2B, B2C, credit note) |
| `erp_overrides/zatca/onboarding.py` | Whitelisted `run` (CSR → compliance CSID → 6 compliance checks → production CSID, new chain) and `renew` (new CSR → renewed CSID, chain kept) |
| `erp_overrides/erp_overrides/doctype/zatca_settings/` | Single doctype: company, environment, seller details, EGS serial, OTP, chain state, certificate expiry, and encrypted credentials (Password fields, stored in the site database and never in git). Has **Onboard** and **Renew CSID** buttons |
| `erp_overrides/erp_overrides/doctype/zatca_submission/` | One row per signed document (the outbox): ICV, UUID, hash, PIH, status, attempts, next automatic attempt, ZATCA's errors and warnings, response, signed and cleared XML |
| `erp_overrides/patches/v1_0/zatca_2026_11.py` | Custom fields. On Sales Invoice: `zatca_status`, `zatca_submission`, `zatca_uuid`, `zatca_qr`. On Address: `zatca_building_number`, `zatca_district`, which ZATCA requires on B2B buyer addresses |
| `erp_overrides/public/js/zatca_sales_invoice.js` | Status indicator, QR code, "Send to ZATCA again" and "ZATCA response" buttons |

### Changed

- `erp_overrides/hooks.py`: Sales Invoice `before_submit`, `on_submit` and `before_cancel`, `doctype_js`, and
  two scheduler entries (`sweep` every 5 minutes, `check_overdue` hourly; both do nothing while ZATCA is off).
  They do nothing unless ZATCA Settings is enabled for the invoice's company, so other companies, such as
  the Zimbabwe demo, are untouched.
- `erp_overrides/patches.txt`: registers `zatca_2026_11`.
- `.gitignore`: `docs/zatca/*.pdf`, `*.pem`, `*.csr`, `*.key`, `zatca_secrets*`.

## Things learned against the sandbox

1. **The SignedProperties layout matters.** ZATCA recomputes the SignedProperties digest over
   the element with one specific indentation. A compact block that is equivalent XML is rejected with
   `signed-properties-hashing`. The **compliance endpoint doesn't check this; the reporting endpoint
   does**, so passing onboarding doesn't prove reporting will work. `crypto.py` keeps the exact layout
   in the document and hashes the same text with its namespace declarations written in.
2. **Two digest encodings.** The invoice hash is base64 of the raw SHA-256 bytes. The certificate digest,
   the SignedProperties digest and the first PIH are base64 of the *hex text* of the SHA-256.
3. **C14N 1.1 vs 1.0.** The spec names C14N 1.1, and lxml only has 1.0. They differ only in
   `xml:id`/`xml:base` handling, which UBL invoices don't use, and the sandbox accepts our hashes.
   The SignedProperties digest is *not* canonical XML at all: the text is hashed with `<ds:DigestMethod …/>`
   left self-closed, which C14N would expand.
4. **The developer portal gives everyone the same production certificate,** one that wasn't issued
   for your key. The sandbox accepts the signatures anyway, so matching key and certificate can only be
   tested in the simulation environment.
5. **The developer portal doesn't detect duplicates or enforce the chain across calls.** A resent invoice
   is cleared or reported again with 200, so the 208/409 handling and chain behaviour need the simulation
   environment for a real test.
6. **Some errors are plain text.** A malformed CSR gets `Invalid Request` and a bad `Accept-Version` gets a
   sentence, not JSON; `Response.summary()` shows them as they are.

## Setup

```bash
bench --site <site> migrate
# optional fictional demo: a Saudi company, VAT 15%, a B2B and a B2C customer, settings filled in
bench --site <site> execute erp_overrides.zatca.demo.seed
bench --site <site> execute erp_overrides.zatca.onboarding.run
bench --site <site> execute erp_overrides.zatca.demo.invoices   # B2B, B2C and a credit note
```

Or by hand:

1. Open **ZATCA Settings** and fill in:
   - Company, VAT number and CRN.
   - Address: street, a 4-digit building number, district, city and a 5-digit postal code.
   - Leave environment `developer-portal` and OTP `123345`.
2. Click **Onboard**. The log at the bottom shows each step.
3. Tick **Send invoices to ZATCA** and save.
4. B2B customers need: type *Company*, a VAT number, and an address with the *Building number (KSA)*
   and *District (KSA)* fields filled.
5. Submit a Sales Invoice in SAR. After a few seconds it shows *ZATCA: Cleared* or *ZATCA: Reported* and a QR code.

## Limits of this POC

- One company and one EGS unit. SAR only. VAT categories S (standard) and Z (zero-rated, with one
  exemption code from settings); E and O aren't mapped.
- No document-level allowances or charges in the XML: ERPNext's `net_rate` already includes them per line.
- Simplified invoices are reported straight after submit, with the outbox catching anything that didn't
  go through. There's no deliberate batching within the 24 hours.
- No bilingual (Arabic/English) print format yet. The QR code is shown on the form.

## What's left

1. Click through the Desk UI in a browser (buttons, indicator, QR) and fix anything that looks off.
2. A GitHub Actions workflow running `erp_overrides/zatca/tests` (the tests exist and pass);
   Frappe integration tests for `send()` and the chain with the ZATCA API mocked.
3. A section in the main README, an hours log, and a screen recording with a redacted sandbox log.

## Running the tests

The pure tests need only `lxml`, `cryptography` and `requests` (no site, no network):

```bash
python -m unittest erp_overrides.zatca.tests.test_pure -v     # or: pytest erp_overrides/zatca/tests
```

## Specifications

The PDFs aren't kept in this repo (`docs/zatca/*.pdf` is git-ignored). Download them from ZATCA:

- Sandbox API reference (Swagger, Sandbox Release 2.1.0), one page per endpoint: compliance CSID,
  compliance invoices, production CSID (onboarding), renewal, clearance, reporting. Export them from the
  [developer portal](https://sandbox.zatca.gov.sa/); kept locally as `compliance_csid.pdf`,
  `compliance_invoice.pdf`, `onboarding.pdf`, `renewal.pdf`, `clearance.pdf` and `reporting.pdf`.

- [E-invoicing Detailed Technical Guideline v2 (Nov 2022)](https://zatca.gov.sa/en/E-Invoicing/Introduction/Guidelines/Documents/E-invoicing-Detailed-Technical-Guideline.pdf): onboarding, signing steps, QR
- [Electronic Invoice XML Implementation Standard v1.2 (May 2023)](https://zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20230519_ZATCA_Electronic_Invoice_XML_Implementation_Standard_%20vF.pdf)
- [Electronic Invoice Security Features Implementation Standards v1.2 (May 2023)](https://zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20230519_ZATCA_Electronic_Invoice_Security_Features_Implementation_Standards_vF.pdf)
- [Detailed Guidelines for E-Invoicing v2 (May 2023)](https://zatca.gov.sa/en/E-Invoicing/Introduction/Guidelines/Documents/E-Invoicing_Detailed__Guideline.pdf): business and legal rules
- [Fatoora Portal User Manual](https://zatca.gov.sa/en/E-Invoicing/Introduction/Guidelines/Documents/Fatoora_Portal_User_Manual_English.pdf)
- [E-Invoicing Resolution](https://zatca.gov.sa/en/RulesRegulations/Taxes/Documents/20210602_ZATCA_Electronic_Invoice_Resolution_English_Vshared.pdf)
- [Security requirements page](https://zatca.gov.sa/en/E-Invoicing/SystemsDevelopers/Pages/Security-Requirements.aspx), where to look for newer releases
- [Developer portal and sandbox](https://sandbox.zatca.gov.sa/): developer portal manual, SDK, validator, API docs

## Prior art

[ERPGulf/zatca_erpgulf](https://github.com/ERPGulf/zatca_erpgulf) (MIT) is an established ZATCA app for
ERPNext. None of its code is used here; this implementation was written from ZATCA's specifications.

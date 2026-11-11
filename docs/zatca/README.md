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

**Not run yet:** the Frappe side, meaning the doctypes, hooks, onboarding button, retry and Desk
script. That code is written and compiles, but it hasn't been migrated onto a site and run (see
[What's left](#whats-left)).

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
- **Cancelling** an invoice ZATCA has accepted is blocked; issue a credit note instead.
- **Standard or simplified:** a customer of type Company with a VAT number (`tax_id`) gets a standard
  invoice; everyone else gets a simplified one. Returns become credit notes (381) and debit notes are 383.

## Files

### Pure modules: no Frappe import, testable with plain pytest

| File | Purpose |
|---|---|
| `erp_overrides/zatca/ubl.py` | Invoice dict → UBL 2.1 XML. Totals are worked out from the lines so they always add up the way the validator checks |
| `erp_overrides/zatca/crypto.py` | secp256k1 key, CSR with ZATCA's subject and SAN fields, invoice hash, ECDSA signature, XAdES block |
| `erp_overrides/zatca/qr.py` | QR code: base64 TLV, tags 1–9 |
| `erp_overrides/zatca/document.py` | One call: dict → signed XML with the QR written in |
| `erp_overrides/zatca/client.py` | FATOORA API client: compliance, production CSID, clearance, reporting |

### Frappe side

| File | Purpose |
|---|---|
| `erp_overrides/zatca/mapping.py` | Sales Invoice → dict; `check()` lists what would make ZATCA reject it, in plain words |
| `erp_overrides/zatca/submit.py` | Doc events, the chain, `send`, whitelisted `retry` and `qr_svg` |
| `erp_overrides/zatca/onboarding.py` | Whitelisted `run`: CSR → compliance CSID → 6 compliance checks → production CSID |
| `erp_overrides/erp_overrides/doctype/zatca_settings/` | Single doctype: company, environment, seller details, EGS serial, OTP, chain state, and encrypted credentials (Password fields, stored in the site database and never in git). Has an **Onboard** button |
| `erp_overrides/erp_overrides/doctype/zatca_submission/` | One row per signed document: ICV, UUID, hash, PIH, status, ZATCA's errors and warnings, response, signed and cleared XML |
| `erp_overrides/patches/v1_0/zatca_2026_11.py` | Custom fields. On Sales Invoice: `zatca_status`, `zatca_submission`, `zatca_uuid`, `zatca_qr`. On Address: `zatca_building_number`, `zatca_district`, which ZATCA requires on B2B buyer addresses |
| `erp_overrides/public/js/zatca_sales_invoice.js` | Status indicator, QR code, "Send to ZATCA again" and "ZATCA response" buttons |

### Changed

- `erp_overrides/hooks.py`: Sales Invoice `before_submit`, `on_submit` and `before_cancel`, plus `doctype_js`.
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
4. **The developer portal gives everyone the same production certificate,** one that wasn't issued
   for your key. The sandbox accepts the signatures anyway, so matching key and certificate can only be
   tested in the simulation environment.

## Setup (once the remaining steps are done)

```bash
bench --site <site> migrate
```

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
- Simplified invoices are reported straight after submit. There's no offline queue or 24-hour batching.
- No bilingual (Arabic/English) print format yet. The QR code is shown on the form.

## What's left

1. Migrate onto the showcase site and run the Frappe side end to end.
2. `erp_overrides/zatca/demo.py`: a fictional Saudi company (SAR, 15% VAT), plus a B2B and a B2C customer.
3. Live run: Onboard, then a B2B invoice, a B2C invoice and a credit note. Then the failure path: a customer
   with a malformed VAT number gets a readable rejection, and fixing it then retrying works without breaking the chain.
4. Unit tests for the pure modules (QR round trip, hash, the signature verifies) plus a GitHub Actions workflow;
   integration tests with the ZATCA API mocked.
5. A section in the main README, an hours log, and a screen recording with a redacted sandbox log.

## Specifications

The PDFs aren't kept in this repo. Download them from ZATCA:

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

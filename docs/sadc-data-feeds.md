# Data feeds across SADC: tenders and exchange rates

The app was built around two daily feeds that matter to any business in Southern Africa:

- **Public tenders.** New government tenders are picked up from the national e-procurement portals, filed against your
  product categories, shown to the sales team on the [Tenders page](sales-pwa.md#tenders-tenders) and emailed as one digest per
  country.
- **Central-bank exchange rates.** The official rate is written into ERPNext's *Currency Exchange* every weekday, so invoices,
  payments and bank lines in a second currency post at the day's rate. The [Accounts app](accounts-pwa.md) flags missing days.

The original version read the **Zimbabwe e-GP** portal and the **Zambia ZPPA** portal for tenders, and the **Reserve Bank of
Zimbabwe**'s daily USD/ZWG sheets for rates. The fetching code isn't in this repo. `erp_overrides/scrapers.py` keeps the same
entry points as small stubs, so everything around them (doctypes, scheduler, Tenders page, digest email, Accounts rates page) is
wired up and works, and it just fetches nothing.

## Where it can go: the SADC region

SADC has 16 member states, and most of them publish both feeds publicly. The same pattern (fetch, map to a doctype, digest)
covers the region:

| Country | Tenders (public procurement) | Exchange rates (central bank) |
|---|---|---|
| Zimbabwe | PRAZ e-GP portal | Reserve Bank of Zimbabwe (USD/ZWG) |
| Zambia | ZPPA e-GP portal | Bank of Zambia (ZMW) |
| South Africa | National Treasury eTender Portal | South African Reserve Bank (ZAR) |
| Botswana | Public Procurement Regulatory Authority | Bank of Botswana (BWP) |
| Namibia | Central Procurement Board of Namibia | Bank of Namibia (NAD) |
| Malawi | Public Procurement and Disposal of Assets Authority | Reserve Bank of Malawi (MWK) |
| Tanzania | PPRA / NeST e-procurement system | Bank of Tanzania (TZS) |
| Mozambique | National public procurement portal | Banco de Moçambique (MZN) |
| Others | National procurement authorities | Central banks of Angola, DRC, Eswatini, Lesotho, Madagascar, Mauritius, Seychelles, Comoros |

Some things that make this worth doing:

- **One ERPNext, many countries.** Each source writes to the same doctypes, and a "country" column is enough for the Tenders
  page and the digest to group by. A business that bids in three countries gets one list, not three portals.
- **Rate pegs are free wins.** The Namibian dollar, Lesotho loti and Eswatini lilangeni trade at par with the rand (the Common
  Monetary Area). With one SARB feed you get four currencies.
- **Categories make it relevant.** Tenders are filtered to the categories a business sells (UNSPSC codes in Eprocure
  Settings), so sales sees ten relevant tenders, not five hundred.
- **ERPNext does the rest.** A tender can become a Lead or Opportunity, and a rate is just a Currency Exchange record that
  every ERPNext document already reads.

Before connecting a source, check its terms of use. Prefer an official API or published feed (OCDS, CSV, RSS) over reading web
pages, and keep request rates polite.

## Connecting a source

Fill in one function in `erp_overrides/scrapers.py`:

| Stub | Returns | Used by |
|---|---|---|
| `fetch_zimbabwe_tenders()` | a list of *Egp Tender* field dicts (keyed by `id`) | `get_tenders`: the Egp Settings button and the 00:00/08:00/16:00 cron |
| `fetch_zambia_tenders()` | a list of *Eprocure Tender* field dicts (keyed by `reference_id`) | `get_zppa_portal_tenders`: the same cron |
| `fetch_rates(start, end)` | `(date, from_currency, to_currency, rate)` tuples | `sync_rates`: the weekday cron and **Fetch from RBZ** in the Accounts app |

New records are inserted and existing ones are skipped. `tender_digest.send_tender_digests` (30 minutes after each tender run)
emails whatever arrived, to the `tender_digest_recipient` set in `site_config.json`.

For another country's tenders, copy the pattern: a doctype (or a country field on an existing one), a `fetch_*` function, a cron
line in `hooks.py`, and a section in `tender_digest.py`.

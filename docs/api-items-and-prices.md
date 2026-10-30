# Fetching Products & Price Lists over the REST API (curl)

How to read **Items** (products), **Price Lists** and **Item Prices** out of the
site over HTTP, and how to filter them. Written against
**Frappe v16 / ERPNext v16**.

Products live in the ERPNext **Item** DocType. Prices are *not* on the Item —
they live in **Item Price** rows, each pointing at one **Price List**. So
"products with their prices" is always Item ⟷ Item Price ⟷ Price List.

---

## 1. Setup: base URL and auth

```bash
export SITE="https://erp.example.com"            # or http://demo.localhost:8000 locally
export KEY="<api_key>"
export SECRET="<api_secret>"
export AUTH="Authorization: token $KEY:$SECRET"
```

Get the key/secret from **User → API Access → Generate Keys** in the desk UI
(`/app/user/<email>`). The `token key:secret` scheme is the one to use for
scripts — no cookies, no CSRF token needed.

Quick sanity check:

```bash
curl -s -H "$AUTH" "$SITE/api/method/frappe.auth.get_logged_user"
# {"message":"api-user@example.com"}
```

> Everything below respects the permissions of the user the key belongs to.
> An empty `data` array usually means *no permission*, not *no records*.

---

## 2. Two API versions — pick one and stay on it

Frappe v16 serves both. They differ in pagination parameter names.

| | v1 (stable, widely used) | v2 (newer) |
|---|---|---|
| List | `GET /api/resource/<DocType>` | `GET /api/v2/document/<DocType>` |
| Single doc | `GET /api/resource/<DocType>/<name>` | `GET /api/v2/document/<DocType>/<name>` |
| Page size | `limit_page_length` | `limit` |
| Offset | `limit_start` | `start` |
| Count | `/api/method/frappe.client.get_count` | `GET /api/v2/doctype/<DocType>/count` |
| Next page hint | — | `has_next_page` in the response |
| `or_filters` | yes | no |

The examples below use **v1** unless marked otherwise, because `or_filters` and
`limit_page_length` are what most existing tooling expects.

---

## 3. Filter syntax

`filters` is a JSON array of `[fieldname, operator, value]` triples, ANDed
together. It must be URL-encoded — `curl -G --data-urlencode` does that for you,
which is why every example uses that form.

```bash
curl -s -G -H "$AUTH" "$SITE/api/resource/Item" \
  --data-urlencode 'fields=["item_code","item_name","item_group","stock_uom"]' \
  --data-urlencode 'filters=[["disabled","=",0],["is_sales_item","=",1]]' \
  --data-urlencode 'limit_page_length=20'
```

The short dict form `filters={"disabled":0}` also works for plain equality.

### Operators

| Operator | Example |
|---|---|
| `=` `!=` `>` `<` `>=` `<=` | `["price_list_rate",">",100]` |
| `like` / `not like` | `["item_name","like","%pump%"]` |
| `in` / `not in` | `["item_group","in",["Products","Services"]]` |
| `between` | `["valid_from","between",["2026-01-01","2026-12-31"]]` |
| `is` | `["valid_upto","is","not set"]` (or `"set"`) |
| `descendants of` | `["item_group","descendants of","All Item Groups"]` |
| `descendants of (inclusive)` | includes the node itself |

`descendants of` matters for **Item Group**, which is a tree — filtering
`item_group = "Raw Material"` misses every child group under it.

### OR conditions (v1 only)

`or_filters` uses the same shape and is ORed with itself, then ANDed with
`filters`:

```bash
curl -s -G -H "$AUTH" "$SITE/api/resource/Item" \
  --data-urlencode 'fields=["item_code","item_name","brand"]' \
  --data-urlencode 'filters=[["disabled","=",0]]' \
  --data-urlencode 'or_filters=[["item_name","like","%valve%"],["description","like","%valve%"]]'
```

### Sorting and pagination

```bash
  --data-urlencode 'order_by=modified desc'
  --data-urlencode 'limit_start=0'
  --data-urlencode 'limit_page_length=100'
```

`limit_page_length=0` returns **all** rows — safe on Price List, dangerous on
Item Price. Prefer paging (§8).

---

## 4. Products (Item)

Useful fields: `item_code`, `item_name`, `item_group`, `brand`, `description`,
`stock_uom`, `sales_uom`, `purchase_uom`, `disabled`, `is_stock_item`,
`is_sales_item`, `is_purchase_item`, `has_variants`, `variant_of`,
`standard_rate`, `valuation_rate`, `image`.

Active sellable products in a group tree, newest first:

```bash
curl -s -G -H "$AUTH" "$SITE/api/resource/Item" \
  --data-urlencode 'fields=["item_code","item_name","item_group","brand","stock_uom","image"]' \
  --data-urlencode 'filters=[["disabled","=",0],["is_sales_item","=",1],["has_variants","=",0],["item_group","descendants of (inclusive)","Products"]]' \
  --data-urlencode 'order_by=item_name asc' \
  --data-urlencode 'limit_page_length=100'
```

One product in full (including child tables — `uoms`, `taxes`, `item_defaults`,
`barcodes`):

```bash
curl -s -H "$AUTH" "$SITE/api/resource/Item/ITEM-0001"
```

Item codes with spaces or slashes must be URL-encoded in the path:

```bash
CODE=$(jq -rn --arg s 'PUMP 1/2 INCH' '$s|@uri')
curl -s -H "$AUTH" "$SITE/api/resource/Item/$CODE"
```

---

## 5. Price Lists

The catalogue of price lists themselves — small table, fetch it all:

```bash
curl -s -G -H "$AUTH" "$SITE/api/resource/Price List" \
  --data-urlencode 'fields=["name","currency","buying","selling","enabled","price_not_uom_dependent"]' \
  --data-urlencode 'filters=[["enabled","=",1],["selling","=",1]]' \
  --data-urlencode 'limit_page_length=0'
```

`buying` and `selling` are flags, and a list can be both. Filter on the one that
matches your use case, otherwise you will price a sales quote off a supplier
list.

---

## 6. Item Prices — the actual prices

Fields: `item_code`, `item_name`, `price_list`, `price_list_rate`, `currency`,
`uom`, `packing_unit`, `valid_from`, `valid_upto`, `customer`, `supplier`,
`batch_no`, `buying`, `selling`, `brand`, `note`, `reference`.

All prices on one price list:

```bash
curl -s -G -H "$AUTH" "$SITE/api/resource/Item Price" \
  --data-urlencode 'fields=["item_code","item_name","uom","price_list_rate","currency","valid_from","valid_upto"]' \
  --data-urlencode 'filters=[["price_list","=","Standard Selling"]]' \
  --data-urlencode 'order_by=item_code asc' \
  --data-urlencode 'limit_page_length=500'
```

Note the space in `Item Price` — with `-G --data-urlencode` curl does *not*
encode the path, so quote the URL (as above) or write `Item%20Price`.

### Prices for a specific set of products

```bash
curl -s -G -H "$AUTH" "$SITE/api/resource/Item Price" \
  --data-urlencode 'fields=["item_code","price_list","price_list_rate","currency","uom"]' \
  --data-urlencode 'filters=[["item_code","in",["ITEM-0001","ITEM-0002","ITEM-0003"]],["selling","=",1]]'
```

### Only prices valid today

An Item Price is current when `valid_from <= today` (or unset) and
`valid_upto >= today` (or unset). The REST filters are pure AND, so "or unset"
needs `or_filters` — two calls, or fetch the dates and evaluate client-side:

```bash
TODAY=$(date +%F)
curl -s -G -H "$AUTH" "$SITE/api/resource/Item Price" \
  --data-urlencode 'fields=["item_code","price_list_rate","valid_from","valid_upto"]' \
  --data-urlencode "filters=[[\"price_list\",\"=\",\"Standard Selling\"],[\"valid_from\",\"<=\",\"$TODAY\"]]" \
  --data-urlencode "or_filters=[[\"valid_upto\",\"is\",\"not set\"],[\"valid_upto\",\">=\",\"$TODAY\"]]"
```

### Customer- or supplier-specific prices

An Item Price with `customer` set applies only to that customer; blank means the
general rate. Same for `supplier` on buying lists.

```bash
# general rates only
--data-urlencode 'filters=[["price_list","=","Standard Selling"],["customer","is","not set"],["supplier","is","not set"]]'

# one customer's negotiated rates
--data-urlencode 'filters=[["price_list","=","Standard Selling"],["customer","=","Acme Ltd"]]'
```

### Price band / currency filters

```bash
--data-urlencode 'filters=[["currency","=","USD"],["price_list_rate","between",[50,500]]]'
```

---

## 7. Joining products and prices

There is no join in the REST API. Two workable patterns:

**A — price-list-first (best for a catalogue export).** Item Price already
carries `item_name` and `brand`, so one call is often enough:

```bash
curl -s -G -H "$AUTH" "$SITE/api/resource/Item Price" \
  --data-urlencode 'fields=["item_code","item_name","brand","uom","price_list","price_list_rate","currency"]' \
  --data-urlencode 'filters=[["price_list","=","Standard Selling"],["selling","=",1]]' \
  --data-urlencode 'limit_page_length=0' | jq '.data'
```

**B — items first, then prices in one batched call.** Pull the item codes, then
feed them back with an `in` filter and merge on `item_code`:

```bash
CODES=$(curl -s -G -H "$AUTH" "$SITE/api/resource/Item" \
  --data-urlencode 'fields=["item_code"]' \
  --data-urlencode 'filters=[["disabled","=",0],["item_group","=","Products"]]' \
  --data-urlencode 'limit_page_length=0' | jq -c '[.data[].item_code]')

curl -s -G -H "$AUTH" "$SITE/api/resource/Item Price" \
  --data-urlencode 'fields=["item_code","price_list","price_list_rate","currency"]' \
  --data-urlencode "filters=[[\"item_code\",\"in\",$CODES],[\"price_list\",\"=\",\"Standard Selling\"]]" \
  --data-urlencode 'limit_page_length=0'
```

Keep the `in` list under a few hundred codes per call — it goes into the SQL
`IN (...)` and into the URL.

### The *effective* rate for a transaction

If you need the rate ERPNext itself would apply (party-specific price, UOM
conversion, pricing rules, currency conversion), don't reimplement it — call
ERPNext's own method:

```bash
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  "$SITE/api/method/erpnext.stock.get_item_details.get_item_details" \
  -d '{
        "args": {
          "item_code": "ITEM-0001",
          "company": "Demo Trading Ltd",
          "customer": "Acme Ltd",
          "currency": "USD",
          "selling_price_list": "Standard Selling",
          "price_list_currency": "USD",
          "plc_conversion_rate": 1,
          "conversion_rate": 1,
          "qty": 10,
          "stock_qty": 10,
          "uom": "Nos",
          "doctype": "Sales Order",
          "transaction_date": "2026-08-27"
        }
      }'
```

The response includes `price_list_rate`, `rate`, `discount_percentage`,
`currency` and the applied `pricing_rules`. For buying, swap `customer` for
`supplier`, `selling_price_list` for `buying_price_list`, and `doctype` for
`"Purchase Order"`.

---

## 8. Counting and paging

```bash
# v1 count
curl -s -G -H "$AUTH" "$SITE/api/method/frappe.client.get_count" \
  --data-urlencode 'doctype=Item Price' \
  --data-urlencode 'filters=[["price_list","=","Standard Selling"]]'

# v2 count
curl -s -G -H "$AUTH" "$SITE/api/v2/doctype/Item%20Price/count" \
  --data-urlencode 'filters={"price_list":"Standard Selling"}'
```

Page through a large price list:

```bash
START=0; PAGE=500
while :; do
  RESP=$(curl -s -G -H "$AUTH" "$SITE/api/resource/Item Price" \
    --data-urlencode 'fields=["item_code","price_list_rate","currency"]' \
    --data-urlencode 'filters=[["price_list","=","Standard Selling"]]' \
    --data-urlencode 'order_by=name asc' \
    --data-urlencode "limit_start=$START" \
    --data-urlencode "limit_page_length=$PAGE")
  N=$(echo "$RESP" | jq '.data | length')
  echo "$RESP" | jq -c '.data[]'
  [ "$N" -lt "$PAGE" ] && break
  START=$((START + PAGE))
done
```

Always set a deterministic `order_by` when paging — without it, rows can repeat
or vanish between pages.

The v2 equivalent uses `start`/`limit` and tells you when to stop via
`has_next_page`:

```bash
curl -s -G -H "$AUTH" "$SITE/api/v2/document/Item%20Price" \
  --data-urlencode 'fields=["item_code","price_list_rate"]' \
  --data-urlencode 'filters={"price_list":"Standard Selling"}' \
  --data-urlencode 'start=0' --data-urlencode 'limit=500'
# → {"data":[...],"has_next_page":true}
```

---

## 9. Discovering fields

Rather than guessing field names:

```bash
curl -s -H "$AUTH" "$SITE/api/v2/doctype/Item%20Price/meta" | jq -r '.data.fields[] | "\(.fieldname)\t\(.fieldtype)\t\(.options // "")"'
```

---

## 10. Gotchas

- **Default page size is 20.** Miss `limit_page_length` and you will quietly get
  20 rows and conclude the data isn't there.
- **`fields` is not optional in practice.** Without it you get only `name`.
- **Prices are not on the Item.** `standard_rate` on Item is just the seed value
  used to create an Item Price on insert; it is not kept in sync afterwards.
- **Multiple prices per item are normal** — different price list, UOM, currency,
  validity window, customer/supplier, or batch. Deduplicate deliberately; the
  precedence ERPNext uses is in `erpnext/stock/get_item_details.py:get_item_price`
  (latest `valid_from`, then batch, then UOM, party-specific over general).
- **UOM matters.** A price with `uom` blank applies to any UOM; one with `uom`
  set applies only to that UOM, unless the Price List has
  `price_not_uom_dependent` ticked.
- **Spaces in DocType names** must be quoted or `%20`-encoded in the path.
- **Child-table rows** (`uoms`, `taxes`, `item_defaults`) don't come back in a
  list call — fetch the single doc, or query the child DocType with a
  `["parent","=","ITEM-0001"]` filter.
- **HTTP 403 with an HTML body** means the key/secret is wrong or the user lacks
  read permission on the DocType.

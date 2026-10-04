# eBay bulk lister (PRODUCTION)

> **Note (Oct 2026):** the owner's live eBay listings were created with a separate tool on the
> owner's computer (`Desktop\EBAY`), not with these scripts. Running `publish` here would use
> different SKUs and create DUPLICATE listings. Only use these scripts again after checking with
> the owner which tool manages the listings.

Lists the products from akiliwomarketplace.com on **ebay.com** with the Sell Inventory API.
This folder starts with `_`, so GitHub Pages does not publish it on the website.

## One-time setup
1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and add your **Cert ID**, **RuName** and ship-from ZIP code.
3. **Business policies:** if you already listed Crystal Hair Removal, your policies already exist, so just run 'policies' to get their IDs and put them in .env. There's no need to create them twice. Policies are **account-wide**: the same shipping, payment and return policy IDs are used for every product, including your book. The script only *reads* policies and never creates any. (No policies yet? Create one of each in Seller Hub > Account > Business policies.)
4. `python ebay_bulk_all_products.py auth`: sign in to eBay once and approve. This saves a refresh token (valid about 18 months).
5. `python ebay_bulk_all_products.py policies`: lists your existing policies. If you have exactly one of each, it prints the 3 lines to paste into `.env`.
   Check that your **shipping** policy suits heavier items too. A free or flat-rate policy set up for the 1.8 oz crystal will also apply to the 22 oz soap pack and the 19 oz tonic bottles.

## Every time
- `python ebay_bulk_all_products.py plan`: dry run. Reads the website, checks every product with eBay (category + required item specifics) and writes `ebay_bulk_upload_all.csv`. **Creates nothing.**
- `python ebay_bulk_all_products.py publish --only LAST-BUS-978`: list one item first and check it on ebay.com.
- `python ebay_bulk_all_products.py publish`: list everything marked READY. Re-running updates existing listings instead of duplicating them.

Products, SKUs, eBay titles, categories, conditions, **weights** and quantities live in the `CATALOG` at the top of the script. Items without a real weight are skipped until you add one.

## Pause / resume your book (Last Bus to Where, SKU LAST-BUS-978)
- `python pause_book.py status`: dry run. Shows whether the book is live on eBay. Changes nothing.
- `python pause_book.py pause`: **ends** the eBay listing (withdraw offer). The inventory item (photos, 9.78 oz weight, item specifics) and the offer (price, category, policies) are **kept as a draft**. Nothing is deleted.
- `python pause_book.py resume --quantity 100`: puts it back on eBay with 100 copies, in one command.

While the SKU is in `PAUSED_ON_EBAY` (top of `ebay_bulk_all_products.py`), a normal bulk `publish` skips it. Don't use quantity 0 to hide a listing: unless "Out-of-stock control" is on in your eBay account, eBay ends the listing anyway, so the script refuses 0.

## Listings you made by hand in Seller Hub (e.g. Crystal Hair Removal, HAIR-005)
The Inventory API can't see listings created in Seller Hub, so the script would otherwise make a **duplicate**. SKUs in `SELLER_HUB_LISTINGS` are therefore **skipped** by `publish` until you migrate them:
1. In Seller Hub, edit the listing and set **Custom label (SKU)** to `HAIR-005`, then save.
2. `python ebay_bulk_all_products.py migrate <eBay item number>`: hands that same listing (same item number, watchers and sales) over to the API. Nothing is ended.
3. From then on, `publish` **updates** that listing, including the 1.785 oz weight, instead of creating a new one.

Note: that update replaces the listing's title, photos, description, price and quantity with the website + CATALOG values (eBay price $15.99 from `ebay_price`, quantity 1). Run `plan` first, and change `qty` in CATALOG if you have more in stock.

## Publish from GitHub (no computer needed after setup)
The workflow `.github/workflows/ebay.yml` runs these same scripts on GitHub's servers.

**One-time setup:** GitHub > this repository > **Settings > Secrets and variables > Actions > New repository secret**. Add:
`EBAY_CLIENT_ID`, `EBAY_CERT_ID`, `EBAY_REFRESH_TOKEN`, `EBAY_FULFILLMENT_POLICY_ID`, `EBAY_PAYMENT_POLICY_ID`, `EBAY_RETURN_POLICY_ID`, `EBAY_LOCATION_CITY`, `EBAY_LOCATION_STATE`, `EBAY_LOCATION_POSTAL`.
The refresh token comes from running `python ebay_bulk_all_products.py auth` once on your computer (it needs you to sign in to eBay in a browser).

**Every time:** GitHub > **Actions > eBay listings > Run workflow**, then pick a command:
- `plan`: dry run, changes nothing
- `policies`: read-only list of your business policy IDs
- `publish`: type `PUBLISH` in the confirm box (optionally set "Only these SKUs", e.g. `CHAR-001` for a first test)
- `migrate`: adopt a Seller Hub listing (item number + `PUBLISH`)
- `book-status` / `book-pause` / `book-resume` (quantity + `PUBLISH`)

Results are in the run log and in the downloadable `ebay-results` file.

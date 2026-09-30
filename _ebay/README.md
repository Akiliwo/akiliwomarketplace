# eBay bulk lister (PRODUCTION)

Lists the products from akiliwomarketplace.com on **ebay.com** with the Sell Inventory API.
This folder starts with `_`, so GitHub Pages does not publish it on the website.

## One-time setup
1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and add your **Cert ID**, **RuName** and ship-from ZIP code.
3. In Seller Hub, turn on **Business policies** and create a shipping, payment and return policy.
4. `python ebay_bulk_all_products.py auth`: sign in to eBay once and approve. This saves a refresh token (valid about 18 months).
5. `python ebay_bulk_all_products.py policies`: copy the three policy IDs into `.env`.

## Every time
- `python ebay_bulk_all_products.py plan`: dry run. Reads the website, checks every product with eBay (category + required item specifics) and writes `ebay_bulk_upload_all.csv`. **Creates nothing.**
- `python ebay_bulk_all_products.py publish --only LAST-BUS-978`: list one item first and check it on ebay.com.
- `python ebay_bulk_all_products.py publish`: list everything marked READY. Re-running updates existing listings instead of duplicating them.

Products, SKUs, eBay titles, categories, conditions, **weights** and quantities live in the `CATALOG` at the top of the script. Items without a real weight are skipped until you add one.

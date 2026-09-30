# Akiliwo Marketplace — working rules

Static single-page site (`index.html`) served by GitHub Pages from `main` at
www.akiliwomarketplace.com. Products live in the `PRODUCTS` array in `index.html`.

## Never break the live site
- Never edit or delete `CNAME` (must stay `www.akiliwomarketplace.com`).
- Push to `main` only. Don't touch GitHub Pages or custom-domain settings.
- Never remove or rename existing products unless the owner asks.
- Don't invent products, prices, conditions or Stripe links. Ask when unsure.
- After every change: load the page in a browser (desktop + phone width), confirm
  no JS errors, no broken images, no horizontal scroll; after pushing, confirm
  `CNAME` is still on `origin/main`.

## "Add product" — image rules (owner's standing instruction)
- Never commit raw photos (JPG/PNG/HEIC straight from a phone) and never embed
  images in `index.html` as `data:` URIs.
- Always compress to WebP, each file under 300 KB, in 3 sizes that fit inside
  200x200, 500x500 and 1000x1000 (no cropping, no upscaling).
- **When a Cloudinary account is configured** (cloud name and upload preset/API key
  provided by the owner as environment secrets, and `res.cloudinary.com` reachable):
  upload the photo to Cloudinary first and put only the Cloudinary URL
  (`https://res.cloudinary.com/<cloud>/image/upload/...`) in the product's `images`.
  `imgSet()` in `index.html` builds the 200/500/1000 WebP/AVIF versions from it.
- **Until then:** save the three WebP files as `images/<product-slug>-200.webp`,
  `-500.webp`, `-1000.webp` and list only the `-1000.webp` path in `images`;
  `imgSet()` picks the right size and images lazy-load.
- Rotate upside-down photos and crop out distracting background before converting.

## Product copy
- Descriptions: honest, based on the photo and well-known facts about the item.
  Mark used items "Used"/"Pre-owned" and mention visible wear (stickers, stains,
  writing, scratches). No fake reviews, star ratings or unverifiable statistics.
- No Stripe branding in visible text. A card-payment link goes in `link`
  (button reads "Buy now with card"); without one, customers see "Order on WhatsApp".

## eBay listing tool (`_ebay/`)
- `_ebay/ebay_bulk_all_products.py` lists website products on eBay PRODUCTION via the
  Sell Inventory API. When a product is added to or renamed on the site, add/update its
  entry in the script's `CATALOG` (keyed by the exact website title) or `SKIP`.
- Use only real, owner-supplied weights and quantities; never guess. Never put website
  links, WhatsApp or phone numbers in eBay descriptions (eBay off-platform policy).
- Secrets live only in `_ebay/.env` (git-ignored). Never ask for or print the Cert ID.
- `_ebay/` starts with `_`, so GitHub Pages (Jekyll) does not publish it. Don't add `.nojekyll`.
- SKUs listed by hand in Seller Hub go in `SELLER_HUB_LISTINGS` (skipped by publish until
  `migrate`), otherwise publish would create a duplicate. The scripts only READ business
  policies (account-wide); never add code that creates policies.

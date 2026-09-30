#!/usr/bin/env python3
"""
Pause / resume the eBay listing for "Last Bus to Where" (SKU LAST-BUS-978) - PRODUCTION.

    python pause_book.py status                 # DEFAULT, dry run: shows what is on eBay. Changes nothing.
    python pause_book.py pause                  # ENDS the eBay listing, keeps everything for later
    python pause_book.py resume --quantity 100  # puts it back on eBay (one command)

How "pause" works: it calls the Inventory API withdrawOffer. That ends the live listing
but KEEPS the inventory item (title, photos, 9.78 oz weight, item specifics) and the offer
(price, category, policies). The offer goes back to UNPUBLISHED, i.e. a ready-to-go draft.
Nothing is deleted.

Why not quantity 0: unless "Out-of-stock control" is switched on in your eBay account,
eBay simply ENDS a listing whose quantity reaches 0 - and publishing with 0 is rejected.
Withdrawing is the clean way to take it down and keep it ready.

Options:
    --sku SKU        another SKU instead of LAST-BUS-978
    --quantity N     (resume) how many copies to list
    --yes            skip the typed confirmation
    --source PATH    (resume) read products from a local index.html instead of the live site
Uses the same .env as ebay_bulk_all_products.py (Cert ID + refresh token live only there).
"""
import argparse
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ebay_bulk_all_products as lister   # noqa: E402  (same folder)
from ebay_bulk_all_products import Ebay, EbayError, MARKETPLACE, load_env   # noqa: E402

BOOK_SKU = "LAST-BUS-978"


def get_state(ebay, token, sku):
    """Return (inventory_item or None, offer or None) for the SKU on eBay US."""
    try:
        _, item = ebay.call("GET", f"/sell/inventory/v1/inventory_item/{urllib.parse.quote(sku)}", token)
    except EbayError as e:
        if e.status != 404:
            raise
        item = None
    try:
        _, data = ebay.call("GET", "/sell/inventory/v1/offer", token,
                            params={"sku": sku, "marketplace_id": MARKETPLACE})
        offers = data.get("offers", [])
    except EbayError as e:
        if e.status != 404:
            raise
        offers = []
    return item, (offers[0] if offers else None)


def describe(item, offer, sku):
    print(f"\nSKU {sku} on eBay (PRODUCTION):")
    if not item:
        print("  Inventory item : NOT FOUND - this SKU was never sent to eBay (nothing to pause).")
        return
    qty = item.get("availability", {}).get("shipToLocationAvailability", {}).get("quantity")
    weight = item.get("packageWeightAndSize", {}).get("weight", {})
    print(f"  Inventory item : KEPT  ({item.get('product', {}).get('title', '')})")
    print(f"                   quantity {qty}, weight {weight.get('value')} {weight.get('unit', '')}")
    if not offer:
        print("  Offer          : none yet (run ebay_bulk_all_products.py publish --only SKU to create one)")
        return
    listing = offer.get("listing") or {}
    price = offer.get("pricingSummary", {}).get("price", {})
    print(f"  Offer          : {offer['offerId']}  status {offer.get('status')}  "
          f"price {price.get('value')} {price.get('currency', '')}  available {offer.get('availableQuantity')}")
    if offer.get("status") == "PUBLISHED":
        print(f"  Listing        : LIVE  https://www.ebay.com/itm/{listing.get('listingId')}  "
              f"({listing.get('listingStatus', 'ACTIVE')}, sold {listing.get('soldQuantity', 0)})")
    else:
        print("  Listing        : NOT LIVE - paused as a draft. Relist with:  python pause_book.py resume")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="status", choices=["status", "pause", "resume"])
    ap.add_argument("--sku", default=BOOK_SKU)
    ap.add_argument("--quantity", type=int, default=None)
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--source", default=None, help="(resume) read products from this index.html path or URL")
    args = ap.parse_args()

    load_env()
    ebay = Ebay()
    print(f"eBay PRODUCTION ({lister.API})")

    if args.command == "resume":
        # Rebuild the offer from the website + CATALOG and publish it (works for a withdrawn offer).
        argv = ["publish", "--only", args.sku]
        if args.quantity is not None:
            argv += ["--quantity", str(args.quantity)]
        if args.yes:
            argv.append("--yes")
        if args.source:
            argv += ["--source", args.source]
        sys.argv = [lister.__file__] + argv
        lister.main()
        token = ebay.user_token()
        describe(*get_state(ebay, token, args.sku), args.sku)
        return

    token = ebay.user_token()
    item, offer = get_state(ebay, token, args.sku)
    describe(item, offer, args.sku)

    if args.command == "status":
        print("\nDry run only - nothing was changed.")
        return

    # pause
    if not offer or offer.get("status") != "PUBLISHED":
        print("\nNothing to pause: there is no live eBay listing for this SKU.")
        return
    print(f"\nThis ENDS eBay listing {offer.get('listing', {}).get('listingId')} but keeps the item and offer as a draft.")
    if not args.yes and input("Type PAUSE to continue: ").strip() != "PAUSE":
        sys.exit("Cancelled. Nothing changed.")
    _, res = ebay.call("POST", f"/sell/inventory/v1/offer/{offer['offerId']}/withdraw", token, {})
    for w in (res or {}).get("warnings", []):
        print(f"  warning: {w.get('message')}")
    print(f"Withdrawn. eBay listing {res.get('listingId') or ''} has ended.")

    # confirm: offer unpublished, inventory item still there
    item, offer = get_state(ebay, token, args.sku)
    describe(item, offer, args.sku)
    if item and offer and offer.get("status") != "PUBLISHED":
        print("\nConfirmed: listing ENDED, inventory item + offer KEPT (nothing deleted).")
    else:
        print("\nCheck Seller Hub > Listings: eBay did not report the expected state.")


if __name__ == "__main__":
    main()

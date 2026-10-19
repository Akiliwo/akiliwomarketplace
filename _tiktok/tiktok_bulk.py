#!/usr/bin/env python3
"""
Akiliwo Marketplace -> TikTok Shop (US) bulk-upload file.

Fills a TikTok Shop Seller Center bulk-upload template (.xlsx) with the products
from index.html, and makes TikTok-ready JPG photos for them.

    python tiktok_bulk.py TEMPLATE.xlsx            # writes  tiktok_upload_<template>.xlsx
    python tiktok_bulk.py TEMPLATE.xlsx --source https://www.akiliwomarketplace.com/

Get the template in Seller Center: Products -> Add products -> Upload in bulk ->
pick a category -> Download template. One template = one TikTok category; only the
products mapped to that category in TIKTOK_CATEGORY below are written into it.

It reuses the eBay tool's CATALOG (SKU, real package weight, quantity, condition) so
weights are typed in one place only. Nothing is sent to TikTok: you upload the file
yourself in Seller Center (Upload in bulk -> Step 2).

Photos: TikTok needs JPG/PNG at a public URL, aspect ratio between 3:4 and 4:3,
longest side at least 600 px, white background. The site's -1000.webp photos are
padded with white to fit that ratio and saved in images/ next to this script. TikTok
copies them when you upload, so the URLs only have to work during the upload.
Commit and push the images BEFORE uploading the spreadsheet.
"""
import argparse
import importlib.util
import math
import re
import sys
from pathlib import Path

try:
    import openpyxl
    from PIL import Image
except ImportError:
    sys.exit("Missing dependency: run  pip install openpyxl pillow")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
IMG_DIR = HERE / "images"
# Public URL of IMG_DIR (the GitHub repo is public). Change the branch if the images
# were pushed somewhere else.
IMG_BASE = ("https://raw.githubusercontent.com/akiliwo/akiliwomarketplace/"
            "claude/affectionate-hawking-vrc7ba/_tiktok/images/")

FIRST_ROW = 7          # template rows 1-6 are TikTok's headers and example
MIN_SIDE = 600         # TikTok minimum for the longest side
MAX_SIDE = 1200        # TikTok maximum

# ----------------------------------------------------------------- TikTok category
# eBay SKU -> category exactly as the template's Category dropdown spells it.
TIKTOK_CATEGORY = {
    "LAST-BUS-978": "Literature & Art/Novel",
    "BK-PENNY-BRUTAL": "Literature & Art/Novel",
    "BK-LARSSON-FIRE": "Literature & Art/Novel",
    "BK-WESTERFELD-PRETTIES": "Literature & Art/Novel",
    "BK-HIGGINS-DANGEROUS": "Literature & Art/Novel",
    "BK-HIGGINS-RECKONING": "Literature & Art/Novel",
    "BK-PATTERSON-8TH": "Literature & Art/Novel",
    "BK-BRADLEY-SURVIVALIST": "Literature & Art/Novel",
    "BK-DUPRAU-EMBER": "Literature & Art/Novel",
    "BK-SAUL-PRESENCE": "Literature & Art/Novel",
}

# Package size in inches (length, width, height) by book format, as measured by the
# owner. None = not supplied yet: those products are left out and listed as NEEDS INFO.
PACKAGE_INCHES = {
    "Hardcover": None,
    "Paperback": None,
}

# Website products with no description of their own (TikTok requires one).
EXTRA_DESC = {
    "LAST-BUS-978": "Last Bus to Where: A Japa Thriller by Jibril Ahmed.\n"
                    "Brand-new paperback. Fiction / thriller, in English.",
}

# California Prop 65 declarations (mandatory for this category). "No" = the book
# contains no listed reproductive toxicants or carcinogens. The owner confirms this.
PROP65 = {"repro": "No", "carcinogen": "No"}


def load_ebay():
    spec = importlib.util.spec_from_file_location(
        "ebay_catalog", ROOT / "_ebay" / "ebay_bulk_all_products.py")
    mod = importlib.util.module_from_spec(spec)
    argv, sys.argv = sys.argv, [sys.argv[0]]
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = argv
    return mod


def read_source(src):
    if src.startswith("http"):
        import requests
        r = requests.get(src.rstrip("/") + "/index.html" if not src.endswith(".html") else src,
                         timeout=30)
        r.raise_for_status()
        return r.text
    return Path(src).read_text(encoding="utf-8")


def tiktok_photo(src, dest):
    """Pad a site photo with white to a 3:4..4:3 frame and save it as a JPG."""
    im = Image.open(src).convert("RGB")
    w, h = im.size
    if w < h * 3 / 4:                       # too tall: widen to 3:4
        cw, ch = math.ceil(h * 3 / 4), h
    elif w > h * 4 / 3:                     # too wide: heighten to 4:3
        cw, ch = w, math.ceil(w * 3 / 4)
    else:
        cw, ch = w, h
    canvas = Image.new("RGB", (cw, ch), (255, 255, 255))
    canvas.paste(im, ((cw - w) // 2, (ch - h) // 2))
    longest = max(cw, ch)
    if longest < MIN_SIDE or longest > MAX_SIDE:
        scale = (MIN_SIDE if longest < MIN_SIDE else MAX_SIDE) / longest
        canvas = canvas.resize((round(cw * scale), round(ch * scale)), Image.LANCZOS)
    dest.parent.mkdir(exist_ok=True)
    canvas.save(dest, "JPEG", quality=88, optimize=True, progressive=True)


def description(p, entry):
    if not p.get("desc") and entry["sku"] in EXTRA_DESC:
        text = EXTRA_DESC[entry["sku"]]
    else:
        text = p.get("desc", "")
        if p.get("benefits"):
            text += "\n\n" + "\n".join("• " + b for b in p["benefits"])
    if entry.get("condition", "NEW") != "NEW":
        text = entry.get("note", "Pre-owned. Please see photos for exact condition.") \
               + "\n\n" + text
    return text.strip()


def product_name(entry):
    name = re.sub(r"\s+NEW$", "", entry["title"])
    if entry.get("condition", "NEW") != "NEW" and "pre-owned" not in name.lower():
        name += " - Pre-owned"
    return name


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("template", help="TikTok bulk-upload template (.xlsx) from Seller Center")
    ap.add_argument("--source", default=str(ROOT / "index.html"),
                    help="local index.html or the website URL")
    ap.add_argument("--out", help="output .xlsx (default: next to this script)")
    args = ap.parse_args()

    eb = load_ebay()
    products = eb.extract_products(read_source(args.source))
    wb = openpyxl.load_workbook(args.template)
    ws = wb["Template"]
    cols = {c.value: c.column for c in ws[1] if c.value}
    allowed = {r[0].value for r in wb["Category"].iter_rows() if r[0].value}

    rows, needs = [], []
    for p in products:
        entry = eb.CATALOG.get(p["title"])
        if not entry or TIKTOK_CATEGORY.get(entry["sku"]) not in allowed:
            continue
        sku = entry["sku"]
        fmt = entry.get("aspects", {}).get("Format", [None])[0]
        dims = PACKAGE_INCHES.get(fmt)
        problems = []
        if entry.get("weight") is None:
            problems.append("no package weight")
        if not dims:
            problems.append(f"no package size for {fmt or 'this format'}")
        if not p.get("images"):
            problems.append("no photo")
        if p.get("badge", "").lower() == "sold out":
            problems.append("sold out on the website")
        if problems:
            needs.append((sku, p["title"], ", ".join(problems)))
            continue

        urls = []
        for n, img in enumerate(p["images"][:9], 1):
            name = f"{sku.lower()}-{n}.jpg"
            tiktok_photo(ROOT / img, IMG_DIR / name)
            urls.append(IMG_BASE + name)
        rows.append({
            "category": TIKTOK_CATEGORY[sku],
            "product_name": product_name(entry),
            "product_description": description(p, entry),
            **{("main_image" if i == 0 else f"image_{i + 1}"): u for i, u in enumerate(urls)},
            "parcel_weight": math.ceil(entry["weight"] / 16 * 100) / 100,   # oz -> lb, round up
            "parcel_length": dims[0], "parcel_width": dims[1], "parcel_height": dims[2],
            "price": float(p["price"].lstrip("$")),
            "quantity": entry.get("qty", 1),
            "seller_sku": sku,
            "special_product_listing_type": "Fixed price",
            "product_property/101395": PROP65["repro"],
            "product_property/101400": PROP65["carcinogen"],
        })

    # clear TikTok's pre-filled first data row, then write ours
    for c in ws[FIRST_ROW]:
        c.value = None
    for r, row in enumerate(rows, FIRST_ROW):
        for key, val in row.items():
            if key in cols:
                ws.cell(r, cols[key], val)

    out = Path(args.out) if args.out else HERE / f"tiktok_upload_{Path(args.template).stem}.xlsx"
    wb.save(out)
    print(f"Wrote {len(rows)} product(s) to {out}")
    for sku, title, why in needs:
        print(f"  NEEDS INFO  {sku:24} {why}   ({title})")


if __name__ == "__main__":
    main()

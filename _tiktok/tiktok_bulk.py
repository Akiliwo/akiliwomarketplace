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
    "LP-CASH-SEVEN-YEAR-ACHE": "Entertainment/CDs, DVDs, & Vinyl Records/Vinyl Records",
    "LP-CARLIN-OCCUPATION-FOOLE": "Entertainment/CDs, DVDs, & Vinyl Records/Vinyl Records",
    "LP-REEVES-PURE-GOLD-V1": "Entertainment/CDs, DVDs, & Vinyl Records/Vinyl Records",
    "LP-ALABAMA": "Entertainment/CDs, DVDs, & Vinyl Records/Vinyl Records",
    "DVD-STIR-ECHOES": "Entertainment/CDs, DVDs, & Vinyl Records/DVD",
    "DVD-MR-MRS-SMITH": "Entertainment/CDs, DVDs, & Vinyl Records/DVD",
    "DVD-TRUE-BLOOD-S1": "Entertainment/CDs, DVDs, & Vinyl Records/DVD",
    "DVD-SWEET-HOME-ALABAMA": "Entertainment/CDs, DVDs, & Vinyl Records/DVD",
    "CD-ELVIS-2ND-TO-NONE": "Video & Music/CDs",
    "CD-KEYS-A-MINOR": "Video & Music/CDs",
    "CD-JUBILEE-JOSIE-V2": "Video & Music/CDs",
    "CD-BIG-BAND-WAR-YEARS": "Video & Music/CDs",
    "XMAS-CAROUSEL": "Festive & Party Supplies/Festive Decorations/Christmas Decor",
    "XMAS-D56-SHINGLE-CREEK": "Festive & Party Supplies/Festive Decorations/Christmas Decor",
    "XMAS-D56-DICKENS-BELL": "Festive & Party Supplies/Festive Decorations/Christmas Decor",
    "XMAS-D56-START-TRADITION": "Festive & Party Supplies/Festive Decorations/Christmas Decor",
}

# Package size in inches (length, width, height) by book format, as measured by the
# owner. None = not supplied yet: those products are left out and listed as NEEDS INFO.
PACKAGE_INCHES = {
    "Hardcover": (8.75, 5.75, 0.75),
    "Paperback": (8.5, 5.5, 0.57),
    "Record": (12.5, 12.5, 0.5),
    "DVD": (10, 7, 1),
    "CD": (10, 7, 1),      # owner: single CDs ship in the DVD mailer
}

# Package size for single products that don't fit their format's standard mailer.
PACKAGE_BY_SKU = {
    "DVD-TRUE-BLOOD-S1": (10, 8, 4),
    # 3-CD box is thicker than a single CD: DVD mailer footprint, 2 in tall (estimate;
    # the owner gave only the weight, 9.86 oz, which is used as is)
    "CD-BIG-BAND-WAR-YEARS": (10, 7, 2),
    "XMAS-CAROUSEL": None,
    # owner measured with a dollar bill (~6.1 in): 1.5 bills long and wide (~9.2 in);
    # height from the photo of the box front; rounded up
    "XMAS-D56-SHINGLE-CREEK": (10, 10, 7),
    # owner: "same" as Shingle Creek (about 1 dollar bill + a few inches); photos show a
    # front taller than wide and an end wider than tall; rounded up
    "XMAS-D56-DICKENS-BELL": (9, 7, 8),
    # owner: 3 dollar bills long, 1.5 wide; height from the photo of the box end; rounded up
    "XMAS-D56-START-TRADITION": (19, 10, 8),
}

# Packed weight in ounces for TikTok when it differs from the eBay CATALOG weight
# (owner-supplied: a record packed in its mailer weighs 14 oz).
PACKED_OZ = {
    "LP-CASH-SEVEN-YEAR-ACHE": 14,
    "LP-CARLIN-OCCUPATION-FOOLE": 14,
    "LP-REEVES-PURE-GOLD-V1": 14,
    "LP-ALABAMA": 14,
    # owner: a DVD packs at 6-7 oz, the True Blood box set at 2-2.5 lb; the top of
    # each range is used so shipping is never under-declared
    "DVD-STIR-ECHOES": 7,
    "DVD-MR-MRS-SMITH": 7,
    "DVD-SWEET-HOME-ALABAMA": 7,
    "CD-KEYS-A-MINOR": 7,
    "CD-JUBILEE-JOSIE-V2": 7,
    "DVD-TRUE-BLOOD-S1": 40,
}

# Website products with no description of their own (TikTok requires one).
EXTRA_DESC = {
    "LAST-BUS-978": "Last Bus to Where: A Japa Thriller by Jibril Ahmed.\n"
                    "Brand-new paperback. Fiction / thriller, in English.",
}

# Extra category attributes per SKU, keyed by the template's row-1 column name.
# Country of origin is printed on the CD case ("Made in ..."); the owner reads it off.
EXTRA_PROPS = {
    "CD-ELVIS-2ND-TO-NONE": {"product_property/100149": None},
    "CD-KEYS-A-MINOR": {"product_property/100149": "United states"},      # "Printed in U.S.A."
    "CD-JUBILEE-JOSIE-V2": {"product_property/100149": "United Kingdom"},  # "Made in England"
    "CD-BIG-BAND-WAR-YEARS": {"product_property/100149": "United states"},  # "Made In USA"
    # Christmas Decor asks about dangerous goods and batteries. The Dept 56 house lights
    # up from a plug-in light cord; the bell tower has no electrics; the owner says the
    # musical carousel takes no batteries.
    "XMAS-CAROUSEL": {"product_property/101619": "No", "product_property/101610": "None"},  # owner: no batteries
    "XMAS-D56-SHINGLE-CREEK": {"product_property/101619": "No", "product_property/101610": "None"},
    "XMAS-D56-DICKENS-BELL": {"product_property/101619": "No", "product_property/101610": "None"},
    "XMAS-D56-START-TRADITION": {"product_property/101619": "No", "product_property/101610": "None"},  # lighted by cord
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
    ap.add_argument("--only", help="comma-separated SKUs, e.g. for products added after an upload")
    args = ap.parse_args()

    eb = load_ebay()
    products = eb.extract_products(read_source(args.source))
    wb = openpyxl.load_workbook(args.template)
    ws = wb["Template"]
    cols = {c.value: c.column for c in ws[1] if c.value}
    allowed = {r[0].value for r in wb["Category"].iter_rows() if r[0].value}
    # columns TikTok marks Mandatory for each category (hidden sheet in the template)
    keys = {c: k for k, c in cols.items()}
    mandatory = {r[0].value: [keys[c.column] for c in r[1:] if c.value == "Mandatory" and c.column in keys]
                 for r in wb["HiddenStyle"].iter_rows() if r[0].value}

    rows, needs = [], []
    for p in products:
        entry = eb.CATALOG.get(p["title"])
        if not entry or TIKTOK_CATEGORY.get(entry["sku"]) not in allowed:
            continue
        sku = entry["sku"]
        if args.only and sku not in args.only.split(","):
            continue
        fmt = entry.get("aspects", {}).get("Format", [None])[0]
        dims = PACKAGE_BY_SKU.get(sku) or PACKAGE_INCHES.get(fmt)
        problems = []
        weight = PACKED_OZ.get(sku, entry.get("weight"))
        if weight is None:
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

        row = {
            "category": TIKTOK_CATEGORY[sku],
            "product_name": product_name(entry),
            "product_description": description(p, entry),
            "main_image": "(photo)",
            "parcel_weight": math.ceil(weight / 16 * 100) / 100,   # oz -> lb, round up
            "parcel_length": dims[0], "parcel_width": dims[1], "parcel_height": dims[2],
            "price": float(p["price"].lstrip("$")),
            "quantity": entry.get("qty", 1),
            "seller_sku": sku,
            "special_product_listing_type": "Fixed price",
            "product_property/101395": PROP65["repro"],
            "product_property/101400": PROP65["carcinogen"],
            **EXTRA_PROPS.get(sku, {}),
        }
        missing = [ws.cell(3, cols[k]).value for k in mandatory.get(row["category"], [])
                   if row.get(k) in (None, "")]
        if missing:
            needs.append((sku, p["title"], "no " + ", ".join(missing)))
            continue

        for n, img in enumerate(p["images"][:9], 1):
            name = f"{sku.lower()}-{n}.jpg"
            tiktok_photo(ROOT / img, IMG_DIR / name)
            row["main_image" if n == 1 else f"image_{n}"] = IMG_BASE + name
        rows.append(row)

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

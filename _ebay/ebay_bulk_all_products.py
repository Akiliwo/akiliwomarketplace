#!/usr/bin/env python3
"""
Akiliwo Marketplace -> eBay (PRODUCTION) bulk lister, using the eBay Sell Inventory API.

It reads the PRODUCTS list straight from https://www.akiliwomarketplace.com/index.html,
matches every product to the CATALOG below (SKU, eBay title, category, condition,
weight, quantity), and creates inventory items -> offers -> published listings.

    python ebay_bulk_all_products.py plan        # DEFAULT. Dry run: scrape, validate, write the CSV.
                                                 # Creates NOTHING on eBay.
    python ebay_bulk_all_products.py auth        # One time: log in to eBay and get a refresh token.
    python ebay_bulk_all_products.py policies    # READ-ONLY: find the business policies you already have.
    python ebay_bulk_all_products.py migrate ITEM_NUMBER
                                                 # Adopt a listing you made by hand in Seller Hub, so
                                                 # publish UPDATES it instead of creating a duplicate.
    python ebay_bulk_all_products.py publish     # REAL listings on ebay.com. Asks you to type PUBLISH first.

Options:
    --source PATH_OR_URL     read products from a local index.html or another URL
    --only SKU1,SKU2         work on just these SKUs (recommended for your first publish)
    --allow-missing-weight   also list items that have no weight in the CATALOG
    --offline                plan without calling eBay (skips category/aspect checks)
    --yes                    publish without the typed confirmation
    --quantity N             with --only: list N copies (e.g. relist your book with 100)

Paused SKUs (PAUSED_ON_EBAY) are never touched by a bulk publish. See pause_book.py.

Secrets come from a .env file next to this script (see .env.example). Never commit .env.

Why two kinds of token:
  * Application token (Client Credentials grant): used ONLY for the Taxonomy API
    (category suggestions + required item specifics). eBay does not allow this token
    to create listings.
  * User token (Authorization Code grant -> long-lived refresh token): required by the
    Inventory API and Account API. Get it once with `auth`; it lasts about 18 months.
"""
import argparse
import base64
import csv
import html
import json
import os
import re
import sys
import urllib.parse
from decimal import Decimal, InvalidOperation
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Missing dependency: run  pip install requests")

HERE = Path(__file__).resolve().parent
SITE = "https://www.akiliwomarketplace.com/"

# ----------------------------------------------------------------- PRODUCTION ONLY
API = "https://api.ebay.com"
AUTH = "https://auth.ebay.com"
MARKETPLACE = "EBAY_US"
CATEGORY_TREE = "0"            # eBay US category tree
SCOPE_APP = "https://api.ebay.com/oauth/api_scope"
SCOPES_USER = [
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/sell.account",
]
CSV_OUT = HERE / "ebay_bulk_upload_all.csv"
RESULTS_OUT = HERE / "ebay_publish_results.csv"

# eBay US leaf categories used for media (verified at run time by the Taxonomy API).
CAT_BOOKS = "261186"     # Books & Magazines > Books
CAT_DVD = "617"          # Movies & TV > DVDs & Blu-ray Discs
CAT_CD = "176984"        # Music > CDs
CAT_RECORDS = "176985"   # Music > Records

USED_BOOK_NOTE = "Pre-owned book in good used condition. Please see photos for exact condition."
USED_MEDIA_NOTE = "Pre-owned in good used condition. Please see photos for exact condition."

# ================================================================== CATALOG
# One entry per product on akiliwomarketplace.com, keyed by the EXACT website title.
#   sku        stable eBay SKU (never change it after listing)
#   title      eBay title, max 80 characters
#   category   eBay leaf category ID, or {"q": "..."} to let eBay suggest one
#   condition  Inventory API condition enum
#   weight     REAL package weight in ounces (None = unknown -> skipped by default)
#   qty        quantity to offer
#   ebay_price optional eBay-only price, e.g. "15.99" (otherwise the website price is used)
#   aspects    item specifics; anything eBay marks as required must be here
#   note       optional condition note for used items
#   confirm    a question that must be answered before listing (item stays NEEDS INFO)
# Weigh items PACKED for shipping when you can; that is what the label is priced on.
def book(sku, title, author, fmt=None, weight=None, **extra):
    aspects = {"Book Title": [extra.pop("book_title")], "Author": [author], "Language": ["English"]}
    if fmt:
        aspects["Format"] = [fmt]
    return dict(sku=sku, title=title, category=CAT_BOOKS, condition="USED_GOOD",
                weight=weight, qty=1, aspects=aspects, note=USED_BOOK_NOTE, **extra)

CATALOG = {
    # ---------------- Health & beauty (new) - weights from your scale ----------------
    "Maxsuri Charcoal Toothpaste (150g)": dict(
        sku="CHAR-001", title="Maxsuri Charcoal Toothpaste 150g Fluoride-Free Activated Charcoal",
        category={"q": "charcoal toothpaste"}, condition="NEW", weight=5.98, qty=1,
        aspects={"Brand": ["Maxsuri"], "Type": ["Toothpaste"]}),
    "Maxactive Plus (125ml)": dict(
        sku="MAX-002", title="Maxsuri Maxactive Plus 125ml Herbal Wellness Supplement for Men",
        category={"q": "herbal supplement liquid"}, condition="NEW", weight=5.99, qty=1,
        aspects={"Brand": ["Maxsuri"], "Formulation": ["Liquid"]}),
    "Maxsuri 6-in-1 Coffee (10 sachets)": dict(
        sku="COF-003", title="Maxsuri 6-in-1 Coffee 10 Sachets Reishi Cordyceps Tongkat Ali Coffee",
        category={"q": "instant coffee sachets"}, condition="NEW", weight=4.22, qty=1,
        aspects={"Brand": ["Maxsuri"]}),
    "Maxsuri Premium Herbal Soap (Single)": dict(
        sku="SOAP-004", title="Maxsuri Premium Herbal Soap Bar Botanical Cleansing Soap Single",
        category={"q": "herbal bar soap"}, condition="NEW", weight=3.275, qty=1,
        aspects={"Brand": ["Maxsuri"], "Type": ["Bar Soap"]}),
    "Akiliwo Crystal Hair Removal": dict(
        sku="HAIR-005", title="Akiliwo Crystal Hair Eraser Painless Reusable Hair Removal Tool",
        category={"q": "crystal hair eraser hair removal"}, condition="NEW", weight=1.785, qty=1,
        ebay_price="15.99",   # eBay price (website is $10.99)
        aspects={"Brand": ["Akiliwo"]},
        extra_html="<p><b>Color:</b> pink or blue. Please send your color choice in eBay messages after purchase.</p>"),
    "Y38 Wireless Ear Cleaner with Camera": dict(
        sku="EAR-006", title="Y38 Wireless Ear Wax Removal Tool with Camera WiFi Otoscope iPhone Android",
        category={"q": "ear wax removal camera"}, condition="NEW", weight=1.83, qty=1,
        aspects={"Brand": ["Unbranded"], "Model": ["Y38"], "Color": ["White"]}),
    "Max Active (10 sachets)": dict(
        sku="SACH-007", title="Maxsuri Max Active Herbal Drink Mix 10 Sachets Men's Wellness",
        category={"q": "herbal supplement powder sachets"}, condition="NEW", weight=4.2, qty=1,  # 10 sachets x 0.42 oz
        aspects={"Brand": ["Maxsuri"], "Formulation": ["Powder"]}),
    "Maxsuri Premium Herbal Soap — 8-in-1 Pack": dict(
        sku="SOAP8-008", title="Maxsuri Premium Herbal Soap 8 Bar Value Pack Botanical Cleansing Bars",
        category={"q": "herbal bar soap"}, condition="NEW", weight=21.98, qty=1,
        aspects={"Brand": ["Maxsuri"], "Type": ["Bar Soap"]}),
    "SURI Herbal Drink (500ml)": dict(
        sku="SURI-009", title="SURI Herbal Drink 500ml Traditional Botanical Wellness Drink",
        category={"q": "herbal tonic drink"}, condition="NEW", weight=19.04, qty=1,
        aspects={"Brand": ["Maxsuri"], "Formulation": ["Liquid"]}),
    "DULU Herbal Tonic (500ml)": dict(
        sku="DULU-010", title="DULU Herbal Tonic 500ml Traditional Herbal Wellness Drink",
        category={"q": "herbal tonic drink"}, condition="NEW", weight=19.14, qty=1,
        aspects={"Brand": ["Maxsuri"], "Formulation": ["Liquid"]}),

    # ---------------- Your own book (new) ----------------
    "Last Bus to Where": dict(
        sku="LAST-BUS-978", title="Last Bus to Where: A Japa Thriller by Jibril Ahmed Paperback NEW",
        category=CAT_BOOKS, condition="NEW", weight=9.78, qty=100,   # owner has 100 copies
        isbn=None,   # put the ISBN here (e.g. "9781234567890") if the book has one
        aspects={"Book Title": ["Last Bus to Where"], "Author": ["Jibril Ahmed"],
                 "Language": ["English"], "Format": ["Paperback"],
                 "Genre": ["Fiction"], "Topic": ["Thriller"]}),

    # ---------------- Used books (weights not measured yet) ----------------
    "Louise Penny - The Brutal Telling - Hardcover - Chief Inspector Gamache Mystery": book(
        "BK-PENNY-BRUTAL", "The Brutal Telling by Louise Penny Hardcover Chief Inspector Gamache #5",
        "Louise Penny", "Hardcover", weight=22.26, book_title="The Brutal Telling"),
    "Stieg Larsson - The Girl Who Played with Fire - Paperback - Millennium #2": book(
        "BK-LARSSON-FIRE", "The Girl Who Played with Fire by Stieg Larsson Paperback Millennium #2",
        "Stieg Larsson", "Paperback", weight=12.8, book_title="The Girl Who Played with Fire"),
    "The House in the Night - Susan Marie Swanson - Board Book - Caldecott Medal": book(
        "BK-HOUSE-NIGHT", "The House in the Night by Susan Marie Swanson Board Book Caldecott",
        "Susan Marie Swanson", "Board Book", weight=16.26, book_title="The House in the Night"),
    "Amy Tan - The Opposite of Fate: A Book of Musings - Hardcover": book(
        "BK-TAN-FATE", "The Opposite of Fate: A Book of Musings by Amy Tan Hardcover",
        "Amy Tan", "Hardcover", weight=16.8, book_title="The Opposite of Fate"),
    "Jamie Sams - Dancing the Dream: The Seven Sacred Paths of Human Transformation - Paperback": book(
        "BK-SAMS-DREAM", "Dancing the Dream by Jamie Sams Seven Sacred Paths Paperback",
        "Jamie Sams", "Paperback", weight=8.04, book_title="Dancing the Dream"),
    "Scott Westerfeld - Pretties - Uglies Series Book 2 - Paperback - Used": book(
        "BK-WESTERFELD-PRETTIES", "Pretties by Scott Westerfeld Paperback Uglies Series Book 2",
        "Scott Westerfeld", "Paperback", weight=11.4, book_title="Pretties"),
    "DIY Wrap Bracelets - Keiko Sakamoto - Paperback - Used": book(
        "BK-WRAP-BRACELETS", "DIY Wrap Bracelets by Keiko Sakamoto 28 Designs Paperback",
        "Keiko Sakamoto", "Paperback", weight=26.88, book_title="DIY Wrap Bracelets"),
    "Writing Fabulous Sentences & Paragraphs - Evan-Moor - Grades 4-6 - Used": book(
        "BK-EVANMOOR-SENTENCES", "Writing Fabulous Sentences & Paragraphs Evan-Moor Grades 4-6 EMC 575",
        "Evan-Moor", "Paperback", weight=11.68, book_title="Writing Fabulous Sentences & Paragraphs"),
    "Baby on the Way - Sears Children's Library - Hardcover - Used": book(
        "BK-SEARS-BABY", "Baby on the Way by William Sears & Martha Sears Hardcover",
        "William Sears", "Hardcover", weight=12.74, book_title="Baby on the Way"),
    "Jack Higgins - On Dangerous Ground - Hardcover - Used": book(
        "BK-HIGGINS-DANGEROUS", "On Dangerous Ground by Jack Higgins Hardcover Sean Dillon Thriller",
        "Jack Higgins", "Hardcover", weight=20.02, book_title="On Dangerous Ground"),
    "Carl N. Degler - Out of Our Past: The Forces That Shaped Modern America - Third Edition - Paperback - Used": book(
        "BK-DEGLER-PAST", "Out of Our Past by Carl N. Degler Third Edition Paperback",
        "Carl N. Degler", "Paperback", weight=18.66, book_title="Out of Our Past"),
    "DK Eyewitness Books - Ancient China - Used": book(
        "BK-DK-ANCIENT-CHINA", "DK Eyewitness Books Ancient China",
        "DK", None, weight=19.88, book_title="Ancient China"),
    "Pete the Cat Plays Hide-and-Seek - Kimberly & James Dean - Used": book(
        "BK-PETE-HIDE-SEEK", "Pete the Cat Plays Hide-and-Seek by Kimberly & James Dean",
        "Kimberly Dean", None, weight=12.6, book_title="Pete the Cat Plays Hide-and-Seek"),
    "Bill O'Reilly & Martin Dugard - Killing Lincoln - Hardcover - Used": book(
        "BK-OREILLY-LINCOLN", "Killing Lincoln by Bill O'Reilly & Martin Dugard Hardcover",
        "Bill O'Reilly", "Hardcover", weight=19.84, book_title="Killing Lincoln"),
    "Rachael Ray - 30-Minute Meals - Paperback Cookbook - Used": book(
        "BK-RAY-30MIN", "Rachael Ray 30-Minute Meals Paperback Cookbook",
        "Rachael Ray", "Paperback", weight=13.26, book_title="30-Minute Meals"),
    "Bill O'Reilly & Martin Dugard - Killing Patton - Hardcover - Used": book(
        "BK-OREILLY-PATTON", "Killing Patton by Bill O'Reilly & Martin Dugard Hardcover",
        "Bill O'Reilly", "Hardcover", weight=20.1, book_title="Killing Patton"),
    "The Littlest Family's Big Day - Emily Winfield Martin - Board Book - Used": book(
        "BK-LITTLEST-FAMILY", "The Littlest Family's Big Day by Emily Winfield Martin Board Book",
        "Emily Winfield Martin", "Board Book", weight=16.06, book_title="The Littlest Family's Big Day"),
    "Touch & Feel Ocean Friends - Baby Board Book - Used": book(
        "BK-OCEAN-FRIENDS", "Touch & Feel Ocean Friends Baby Board Book",
        "Unknown", "Board Book", weight=11.52, book_title="Touch & Feel Ocean Friends"),
    "James Patterson & Maxine Paetro - The 8th Confession - Paperback - Used": book(
        "BK-PATTERSON-8TH", "The 8th Confession by James Patterson & Maxine Paetro Paperback",
        "James Patterson", "Paperback", weight=7.14, book_title="The 8th Confession"),
    "Arthur T. Bradley - The Survivalist: Frontier Justice - Paperback - Used": book(
        "BK-BRADLEY-SURVIVALIST", "The Survivalist: Frontier Justice by Arthur T. Bradley Paperback",
        "Arthur T. Bradley", "Paperback", weight=11.96, book_title="The Survivalist: Frontier Justice"),
    "Dr. Seuss - Oh, the Places You'll Go! - Hardcover - Used": book(
        "BK-SEUSS-PLACES", "Oh, the Places You'll Go! by Dr. Seuss Hardcover",
        "Dr. Seuss", "Hardcover", weight=13.38, book_title="Oh, the Places You'll Go!"),
    "Getting to Maybe: How to Excel on Law School Exams - Fischl & Paul - Paperback - Used": book(
        "BK-GETTING-TO-MAYBE", "Getting to Maybe How to Excel on Law School Exams Fischl & Paul Paperback",
        "Richard Michael Fischl", "Paperback", weight=16.94, book_title="Getting to Maybe"),
    "Jeanne DuPrau - The City of Ember - Deluxe Edition - Paperback - Used": book(
        "BK-DUPRAU-EMBER", "The City of Ember Deluxe Edition by Jeanne DuPrau Paperback",
        "Jeanne DuPrau", "Paperback", weight=11.46, book_title="The City of Ember"),
    "Jack Higgins - Day of Reckoning - Hardcover - Used": book(
        "BK-HIGGINS-RECKONING", "Day of Reckoning by Jack Higgins Hardcover Sean Dillon Thriller",
        "Jack Higgins", "Hardcover", weight=21.52, book_title="Day of Reckoning"),
    "Hannah Brown - God Bless This Mess - Hardcover Memoir - Used": book(
        "BK-BROWN-MESS", "God Bless This Mess by Hannah Brown Hardcover Memoir",
        "Hannah Brown", "Hardcover", weight=16.9, book_title="God Bless This Mess"),
    "John Saul - The Presence - Hardcover - Used": book(
        "BK-SAUL-PRESENCE", "The Presence by John Saul Hardcover",
        "John Saul", "Hardcover", weight=20.3, book_title="The Presence"),
    "A Framework for Understanding Poverty - Ruby K. Payne, Ph.D. - Paperback - Used": book(
        "BK-PAYNE-POVERTY", "A Framework for Understanding Poverty by Ruby K. Payne Paperback",
        "Ruby K. Payne", "Paperback", weight=12.62, book_title="A Framework for Understanding Poverty"),

    # ---------------- Used DVDs & CDs ----------------
    "Stir of Echoes - Kevin Bacon - DVD - Used": dict(
        sku="DVD-STIR-ECHOES", title="Stir of Echoes DVD Kevin Bacon Supernatural Thriller",
        category=CAT_DVD, condition="USED_GOOD", weight=4.055, qty=1, note=USED_MEDIA_NOTE,
        aspects={"Movie/TV Title": ["Stir of Echoes"], "Format": ["DVD"]}),
    "Mr. & Mrs. Smith - DVD - Widescreen - Used": dict(
        sku="DVD-MR-MRS-SMITH", title="Mr. & Mrs. Smith DVD Widescreen Brad Pitt Angelina Jolie",
        category=CAT_DVD, condition="USED_GOOD", weight=4.545, qty=1, note=USED_MEDIA_NOTE,
        aspects={"Movie/TV Title": ["Mr. & Mrs. Smith"], "Format": ["DVD"]}),
    "True Blood - The Complete First Season - DVD Box Set - Used": dict(
        sku="DVD-TRUE-BLOOD-S1", title="True Blood The Complete First Season DVD Box Set HBO",
        category=CAT_DVD, condition="USED_GOOD", weight=14.64, qty=1, note=USED_MEDIA_NOTE,
        aspects={"Movie/TV Title": ["True Blood"], "Format": ["DVD"], "Season": ["1"]}),
    "Elvis Presley - 2nd to None - CD - Used": dict(
        sku="CD-ELVIS-2ND-TO-NONE", title="Elvis Presley 2nd to None CD Greatest Hits",
        category=CAT_CD, condition="USED_GOOD", weight=4.415, qty=1, note=USED_MEDIA_NOTE,
        aspects={"Artist": ["Elvis Presley"], "Release Title": ["2nd to None"], "Format": ["CD"]}),
    "Jubilee & Josie R&B Vocal Groups Volume Two - CD - Used": dict(
        sku="CD-JUBILEE-JOSIE-V2", title="Jubilee & Josie R&B Vocal Groups Volume Two CD Orioles Charioteers Doo-Wop",
        category=CAT_CD, condition="USED_GOOD", weight=3.90, qty=1, note=USED_MEDIA_NOTE,
        aspects={"Artist": ["Various Artists"], "Release Title": ["Jubilee & Josie R&B Vocal Groups Volume Two"],
                 "Format": ["CD"], "Genre": ["R&B & Soul"]}),
    "Rosanne Cash - Seven Year Ache - Vinyl LP Record - Used": dict(
        sku="LP-CASH-SEVEN-YEAR-ACHE", title="Rosanne Cash Seven Year Ache Vinyl LP Record 1981",
        category=CAT_RECORDS, condition="USED_GOOD", weight=4.93, qty=1, note=USED_MEDIA_NOTE,
        aspects={"Artist": ["Rosanne Cash"], "Release Title": ["Seven Year Ache"], "Format": ["Record"]}),
    "George Carlin - Occupation: Foole - Vinyl LP Record - Used": dict(
        sku="LP-CARLIN-OCCUPATION-FOOLE", title="George Carlin Occupation: Foole Vinyl LP Comedy Record 1973",
        category=CAT_RECORDS, condition="USED_GOOD", weight=8.24, qty=1,
        note="Pre-owned. Cover shows wear, including some water staining and a crease. Please see photos.",
        aspects={"Artist": ["George Carlin"], "Release Title": ["Occupation: Foole"], "Format": ["Record"]}),
    "Jim Reeves - Pure Gold Volume One - Vinyl LP Record - Used": dict(
        sku="LP-REEVES-PURE-GOLD-V1", title="Jim Reeves Pure Gold Volume One Vinyl LP RCA ANL1-3014 Stereo Country",
        category=CAT_RECORDS, condition="USED_GOOD", weight=6.02, qty=1, note=USED_MEDIA_NOTE,
        aspects={"Artist": ["Jim Reeves"], "Release Title": ["Pure Gold Volume One"], "Format": ["Record"],
                 "Record Label": ["RCA"], "Genre": ["Country"]}),
    "Alabama - Vinyl LP Record - Used": dict(
        sku="LP-ALABAMA", title="Alabama Vinyl LP Record Country",
        category=CAT_RECORDS, condition="USED_GOOD", weight=3.895, qty=1, note=USED_MEDIA_NOTE,
        aspects={"Artist": ["Alabama"], "Format": ["Record"], "Genre": ["Country"]}),
    "Godzilla Super Kaiju SpaceGodzilla '94 Action Figure (in Box)": dict(
        sku="TOY-SPACEGODZILLA-94", title="Godzilla Super Kaiju SpaceGodzilla '94 Action Figure in Box",
        category={"q": "Godzilla action figure"}, condition="NEW", weight=12.62, qty=1,
        confirm="is it new/unopened or used? - set condition (NEW or USED_EXCELLENT) then confirm=None",
        aspects={"Character": ["SpaceGodzilla"]}),
    "Alicia Keys - Songs in A Minor - CD - Used": dict(
        sku="CD-KEYS-A-MINOR", title="Alicia Keys Songs in A Minor CD 2001",
        category=CAT_CD, condition="USED_GOOD", weight=3.53, qty=1, note=USED_MEDIA_NOTE,
        aspects={"Artist": ["Alicia Keys"], "Release Title": ["Songs in A Minor"], "Format": ["CD"]}),

    # ---------------- Vintage Christmas (used) ----------------
    "Department 56 Shingle Creek House (Lighted) - Used": dict(
        sku="XMAS-D56-SHINGLE-CREEK", title="Department 56 Heritage Village Shingle Creek House Lighted Christmas Village",
        category={"q": "Department 56 village house"}, condition="USED_EXCELLENT", weight=28.02, qty=1,
        note="Pre-owned. Comes in protective foam packaging with light cord. Please see photos.",
        aspects={"Brand": ["Department 56"]}),
    "Department 56 Dickens' Village Bell Tower with Children - Used": dict(
        sku="XMAS-D56-DICKENS-BELL", title="Department 56 Dickens' Village Bell Tower with Children in Box",
        category={"q": "Department 56 Dickens Village"}, condition="USED_EXCELLENT", weight=17.18, qty=1,
        note="Pre-owned, in its box. The box shows some shelf wear. Please see photos.",
        aspects={"Brand": ["Department 56"]}),
    "Vintage Christmas Musical Carousel (Merry-Go-Round) - Used": dict(
        sku="XMAS-CAROUSEL", title="Vintage Christmas Musical Carousel Merry-Go-Round Train Holly Decor",
        category={"q": "christmas musical carousel"}, condition="USED_EXCELLENT", weight=42.32, qty=1,
        note="Pre-owned vintage piece. Please see photos for condition.",
        aspects={"Brand": ["Unbranded"]}),
}

# Products on the website that are deliberately NOT listed, with the reason.
SKIP = {
    "Kids' Pajama Set — Blue (Top & Bottom)": "website shows a sample drawing, not a real photo",
    "Kids' Pajama Set — Pink (Top & Bottom)": "website shows a sample drawing, not a real photo",
    "Big Boxed Special - Used Book / DVD / CD Bundle Lot - Sale": "no photo; contents of the bundle unknown",
    "Broken Little - Used Book - Memoir / Fiction - $5.00": "no photo or author yet (owner weighed 'Broken Little Believer' at 17.34 oz)",
    "Bill O'Reilly - Used Book - Book #2 - Bestselling History Series": "no photo; exact book unknown",
}

# SKUs kept OFF eBay for now. A bulk `publish` skips them; they are only relisted when
# named explicitly (`publish --only SKU`) or with `pause_book.py resume`.
PAUSED_ON_EBAY = {
    "LAST-BUS-978": "selling on akiliwomarketplace.com first; relist with pause_book.py resume",
}

# SKUs that are ALREADY LIVE on eBay because you listed them by hand in Seller Hub.
# The Inventory API cannot see Seller Hub listings, so publishing these would create a
# DUPLICATE. They are skipped until you run `migrate <listing id>`, which hands the
# existing listing over to the Inventory API; after that, publish updates it in place.
SELLER_HUB_LISTINGS = {
    "HAIR-005": "Akiliwo Crystal Hair Removal (listed by hand in Seller Hub)",
}

VALID_CONDITIONS = {"NEW", "LIKE_NEW", "NEW_OTHER", "USED_EXCELLENT", "USED_VERY_GOOD",
                    "USED_GOOD", "USED_ACCEPTABLE", "FOR_PARTS_OR_NOT_WORKING"}


# ================================================================== helpers
def load_env():
    """Minimal .env reader (KEY=VALUE lines). Real environment variables win."""
    for path in (HERE / ".env", Path.cwd() / ".env"):
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            return path
    return None


def env(name, required=True):
    val = os.environ.get(name, "").strip()
    if required and not val:
        sys.exit(f"Missing {name} in .env (see .env.example).")
    return val


def extract_products(page):
    """Return the PRODUCTS array from index.html as Python dicts.
    Converts the JS object literal to JSON: drops comments outside strings,
    quotes bare keys, normalises quotes and removes trailing commas."""
    start = page.index("const PRODUCTS = [") + len("const PRODUCTS = ")
    out, i, depth = [], start, 0
    while True:
        c = page[i]
        if c in "\"'`":
            j = i + 1
            while page[j] != c:
                j += 2 if page[j] == "\\" else 1
            lit = page[i:j + 1]
            if c != '"':
                lit = json.dumps(lit[1:-1].replace('\\' + c, c))
            out.append(lit)
            i = j + 1
            continue
        if page.startswith("//", i):
            i = page.index("\n", i)
            continue
        if page.startswith("/*", i):
            i = page.index("*/", i) + 2
            continue
        if c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
        out.append(c)
        i += 1
        if depth == 0:
            break
    js = "".join(out)
    js = re.sub(r'([{,]\s*)([A-Za-z_$][\w$]*)\s*:', r'\1"\2":', js)
    js = re.sub(r',(\s*[}\]])', r'\1', js)
    return json.loads(js)


def small_photo(url):
    """Longest side in px if a site photo (found locally in the repo) is under eBay's 500px minimum."""
    if not url.startswith(SITE):
        return None
    local = HERE.parent / url[len(SITE):]
    if not local.exists():
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    with Image.open(local) as im:
        longest = max(im.size)
    return longest if longest < 500 else None


def read_site(source):
    if re.match(r"https?://", source):
        r = requests.get(source, timeout=30)
        r.raise_for_status()
        return r.text
    return Path(source).read_text(encoding="utf-8")


def money(p):
    """Price string from the site product ('$19.99'); uses the first format if present."""
    raw = (p.get("formats") or [{}])[0].get("price") or p.get("price", "")
    try:
        val = Decimal(re.sub(r"[^\d.]", "", raw))
    except InvalidOperation:
        return None
    return f"{val:.2f}" if val > 0 else None


def image_urls(p, base):
    urls = [urllib.parse.urljoin(base, u) for u in (p.get("images") or []) if not u.startswith("data:")]
    return urls[:24]


NO_LINKS = re.compile(r"https?://\S+|www\.\S+|whatsapp|\+?1?\s?720[\s.-]?799[\s.-]?4089", re.I)


def clean(text):
    """Escape for HTML and strip anything eBay treats as an off-eBay contact/link."""
    text = NO_LINKS.sub("", str(text)).replace("**", "")
    return html.escape(text.strip())


def description(p, item):
    parts = [f"<h2>{clean(item['title'])}</h2>"]
    for key in ("tagline", "hook"):
        if p.get(key):
            parts.append(f"<p><i>{clean(p[key])}</i></p>")
    if p.get("desc"):
        parts.append(f"<p>{clean(p['desc'])}</p>")
    for para in p.get("story") or []:
        parts.append(f"<p>{clean(para)}</p>")
    bullets = (p.get("highlights") or []) + (p.get("benefits") or [])
    if bullets:
        parts.append("<ul>" + "".join(f"<li>{clean(b)}</li>" for b in bullets) + "</ul>")
    if p.get("details"):
        parts.append("<ul>" + "".join(f"<li><b>{clean(k)}:</b> {clean(v)}</li>" for k, v in p["details"]) + "</ul>")
    if item.get("extra_html"):
        parts.append(item["extra_html"])
    if p.get("disclaimer"):
        parts.append(f"<p><small><i>{clean(p['disclaimer'])}</i></small></p>")
    parts.append("<p>Ships from Colorado, USA. Thank you for shopping with Akiliwo Marketplace!</p>")
    return "\n".join(parts)


# ================================================================== eBay HTTP
class Ebay:
    def __init__(self):
        self.s = requests.Session()
        self._app = None
        self._user = None

    def _basic(self):
        raw = f"{env('EBAY_CLIENT_ID')}:{env('EBAY_CERT_ID')}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    def _token(self, data):
        r = self.s.post(f"{API}/identity/v1/oauth2/token", data=data, timeout=30,
                        headers={"Authorization": self._basic(),
                                 "Content-Type": "application/x-www-form-urlencoded"})
        if r.status_code != 200:
            sys.exit(f"OAuth error {r.status_code}: {r.text}")
        return r.json()

    def app_token(self):          # Client Credentials grant -> Taxonomy API only
        if not self._app:
            self._app = self._token({"grant_type": "client_credentials", "scope": SCOPE_APP})["access_token"]
        return self._app

    def user_token(self):         # refresh token -> Inventory + Account APIs
        if not self._user:
            rt = env("EBAY_REFRESH_TOKEN", required=False)
            if not rt:
                sys.exit("No EBAY_REFRESH_TOKEN in .env. Run:  python ebay_bulk_all_products.py auth")
            self._user = self._token({"grant_type": "refresh_token", "refresh_token": rt,
                                      "scope": " ".join(SCOPES_USER)})["access_token"]
        return self._user

    def call(self, method, path, token, body=None, params=None, ok=(200, 201, 204), lang=False):
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if lang:
            headers["Content-Language"] = "en-US"
        r = self.s.request(method, API + path, headers=headers, params=params, timeout=60,
                           data=None if body is None else json.dumps(body))
        data = r.json() if r.content and "json" in r.headers.get("Content-Type", "") else {}
        if r.status_code not in ok:
            raise EbayError(r.status_code, data or r.text)
        return r.status_code, data


class EbayError(Exception):
    def __init__(self, status, data):
        self.status, self.data = status, data
        msgs = []
        if isinstance(data, dict):
            for e in data.get("errors", []) + data.get("warnings", []):
                msgs.append(f"[{e.get('errorId')}] {e.get('longMessage') or e.get('message')}")
        super().__init__(f"HTTP {status}: " + ("; ".join(msgs) or str(data)[:500]))


# ================================================================== taxonomy checks
_aspect_cache, _cat_names = {}, {}


def resolve_category(ebay, item):
    cat = item["category"]
    if isinstance(cat, str):
        return cat
    _, data = ebay.call("GET", f"/commerce/taxonomy/v1/category_tree/{CATEGORY_TREE}/get_category_suggestions",
                        ebay.app_token(), params={"q": cat["q"]})
    sugg = data.get("categorySuggestions") or []
    if not sugg:
        raise ValueError(f"eBay has no category suggestion for '{cat['q']}'")
    c = sugg[0]["category"]
    _cat_names[c["categoryId"]] = " > ".join([a["categoryName"] for a in reversed(sugg[0].get("categoryTreeNodeAncestors", []))] + [c["categoryName"]])
    return c["categoryId"]


def required_aspects(ebay, category_id):
    if category_id not in _aspect_cache:
        _, data = ebay.call("GET", f"/commerce/taxonomy/v1/category_tree/{CATEGORY_TREE}/get_item_aspects_for_category",
                            ebay.app_token(), params={"category_id": category_id})
        _aspect_cache[category_id] = [a["localizedAspectName"] for a in data.get("aspects", [])
                                      if a.get("aspectConstraint", {}).get("aspectRequired")]
    return _aspect_cache[category_id]


# ================================================================== planning
def build_plan(args, ebay):
    page = read_site(args.source)
    base = args.source if re.match(r"https?://", args.source) else SITE
    products = extract_products(page)
    only = {s.strip() for s in args.only.split(",")} if args.only else None
    rows, seen = [], set()

    for p in products:
        title = p.get("title", "")
        if p.get("category") == "digital":
            rows.append(dict(site_title=title, status="SKIP", reason="digital product (physical only)"))
            continue
        if title in SKIP:
            rows.append(dict(site_title=title, status="SKIP", reason=SKIP[title], price=money(p)))
            continue
        item = CATALOG.get(title)
        if not item:
            rows.append(dict(site_title=title, status="SKIP", reason="not in CATALOG yet - add an entry"))
            continue
        seen.add(title)
        if only and item["sku"] not in only:
            continue
        if item["sku"] in PAUSED_ON_EBAY and not only:
            rows.append(dict(site_title=title, sku=item["sku"], title=item["title"], price=money(p),
                             weight=item.get("weight"), qty=item.get("qty", 1), condition=item["condition"],
                             status="PAUSED", reason=PAUSED_ON_EBAY[item["sku"]]))
            continue
        row = dict(site_title=title, item=item, product=p, sku=item["sku"], title=item["title"],
                   price=item.get("ebay_price") or money(p), weight=item.get("weight"), qty=args.quantity or item.get("qty", 1),
                   condition=item["condition"], images=image_urls(p, base), problems=[])
        prob = row["problems"]
        if len(item["title"]) > 80:
            prob.append(f"eBay title is {len(item['title'])} chars (max 80)")
        if not row["price"]:
            prob.append("no price on the website")
        if not row["images"]:
            prob.append("no photos")
        if item["condition"] not in VALID_CONDITIONS:
            prob.append(f"bad condition {item['condition']}")
        if item.get("confirm"):
            prob.append("confirm: " + item["confirm"])
        for u in row["images"]:
            small = small_photo(u)
            if small:
                prob.append(f"photo {u.rsplit('/', 1)[-1]} is only {small}px; eBay needs 500px+ - send a bigger photo")
        if row["weight"] is None and not args.allow_missing_weight:
            prob.append("no weight yet - weigh it and add weight= in CATALOG")

        row["category_id"] = item["category"] if isinstance(item["category"], str) else f"auto: {item['category']['q']}"
        if not args.offline and not prob:
            try:
                cid = resolve_category(ebay, item)
                row["category_id"] = cid
                row["category_name"] = _cat_names.get(cid, "")
                missing = [a for a in required_aspects(ebay, cid) if a not in item.get("aspects", {})]
                if missing:
                    prob.append("add required item specifics: " + ", ".join(missing))
            except (EbayError, ValueError) as e:
                prob.append(f"category check failed: {e}")
        row["status"] = "READY" if not prob else "NEEDS INFO"
        row["reason"] = "; ".join(prob)
        rows.append(row)

    for t in CATALOG:
        if t not in seen and not only:
            rows.append(dict(site_title=t, status="SKIP", reason="in CATALOG but no longer on the website"))
    return rows


def write_csv(rows):
    with CSV_OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Title", "SKU", "Price", "Weight (oz)", "Quantity", "Condition", "Category", "Status", "Notes"])
        for r in rows:
            w.writerow([r.get("title") or r["site_title"], r.get("sku", ""), r.get("price") or "",
                        "" if r.get("weight") is None else r["weight"], r.get("qty", ""),
                        r.get("condition", ""), (r.get("category_id") or "") + (f" ({r['category_name']})" if r.get("category_name") else ""),
                        r["status"], r.get("reason", "")])
    return CSV_OUT


def print_plan(rows):
    for st in ("READY", "NEEDS INFO", "PAUSED", "SKIP"):
        group = [r for r in rows if r["status"] == st]
        if not group:
            continue
        print(f"\n== {st} ({len(group)})")
        for r in group:
            head = f"  {r.get('sku', '-'):24} ${r.get('price') or '-':>6}  " if st != "SKIP" else "  "
            w = f"{r['weight']} oz  " if r.get("weight") is not None else ""
            print(f"{head}{w}{(r.get('title') or r['site_title'])[:70]}")
            if r.get("reason"):
                print(f"      -> {r['reason']}")


# ================================================================== publishing
def ensure_location(ebay, token):
    key = env("EBAY_LOCATION_KEY", required=False) or "akiliwo-colorado"
    try:
        ebay.call("GET", f"/sell/inventory/v1/location/{key}", token)
        return key
    except EbayError as e:
        if e.status != 404:
            raise
    body = {"location": {"address": {"city": env("EBAY_LOCATION_CITY"),
                                     "stateOrProvince": env("EBAY_LOCATION_STATE"),
                                     "postalCode": env("EBAY_LOCATION_POSTAL"),
                                     "country": env("EBAY_LOCATION_COUNTRY", required=False) or "US"}},
            "locationTypes": ["WAREHOUSE"], "name": "Akiliwo Marketplace", "merchantLocationStatus": "ENABLED"}
    ebay.call("POST", f"/sell/inventory/v1/location/{key}", token, body)
    print(f"Created inventory location '{key}'.")
    return key


def inventory_item_body(row):
    item, p = row["item"], row["product"]
    product = {"title": item["title"], "description": re.sub(r"<[^>]+>", " ", description(p, item))[:4000],
               "imageUrls": row["images"],
               "aspects": item.get("aspects", {})}
    if item.get("isbn"):
        product["isbn"] = [item["isbn"]]
    body = {"availability": {"shipToLocationAvailability": {"quantity": row["qty"]}},
            "condition": item["condition"], "product": product}
    if item["condition"] != "NEW" and item.get("note"):
        body["conditionDescription"] = item["note"][:1000]
    if row["weight"] is not None:
        body["packageWeightAndSize"] = {"weight": {"value": row["weight"], "unit": "OUNCE"}}
    return body


def offer_body(row, location_key):
    return {"sku": row["sku"], "marketplaceId": MARKETPLACE, "format": "FIXED_PRICE",
            "availableQuantity": row["qty"], "categoryId": row["category_id"],
            "listingDescription": description(row["product"], row["item"]),
            "listingDuration": "GTC",
            "listingPolicies": {"fulfillmentPolicyId": env("EBAY_FULFILLMENT_POLICY_ID"),
                                "paymentPolicyId": env("EBAY_PAYMENT_POLICY_ID"),
                                "returnPolicyId": env("EBAY_RETURN_POLICY_ID")},
            "merchantLocationKey": location_key,
            "pricingSummary": {"price": {"value": row["price"], "currency": "USD"}}}


def publish(args, ebay, rows):
    ready = [r for r in rows if r["status"] == "READY"]
    if not ready:
        print("\nNothing is READY to publish.")
        return
    for k in ("EBAY_FULFILLMENT_POLICY_ID", "EBAY_PAYMENT_POLICY_ID", "EBAY_RETURN_POLICY_ID"):
        env(k)
    print(f"\nAbout to create {len(ready)} REAL eBay listings on ebay.com (PRODUCTION).")
    if not args.yes and input("Type PUBLISH to continue: ").strip() != "PUBLISH":
        sys.exit("Cancelled. Nothing was listed.")

    token = ebay.user_token()
    location = ensure_location(ebay, token)
    results = []
    for r in ready:
        sku = r["sku"]
        if sku in SELLER_HUB_LISTINGS and not has_api_offer(ebay, token, sku):
            print(f"  SKIPPED  {sku:24} already live in Seller Hub - not creating a duplicate.\n"
                  f"           Run:  python ebay_bulk_all_products.py migrate <eBay item number>")
            results.append([sku, r["title"], r["price"], "", "", "SKIPPED", "Seller Hub listing not migrated"])
            continue
        try:
            ebay.call("PUT", f"/sell/inventory/v1/inventory_item/{urllib.parse.quote(sku)}", token,
                      inventory_item_body(r), lang=True)
            body = offer_body(r, location)
            try:
                _, found = ebay.call("GET", "/sell/inventory/v1/offer", token,
                                     params={"sku": sku, "marketplace_id": MARKETPLACE})
                offers = found.get("offers", [])
            except EbayError as e:
                if e.status != 404:
                    raise
                offers = []
            if offers:
                offer_id = offers[0]["offerId"]
                upd = {k: v for k, v in body.items() if k not in ("sku", "marketplaceId", "format")}
                ebay.call("PUT", f"/sell/inventory/v1/offer/{offer_id}", token, upd, lang=True)
            else:
                _, created = ebay.call("POST", "/sell/inventory/v1/offer", token, body, lang=True)
                offer_id = created["offerId"]
            _, pub = ebay.call("POST", f"/sell/inventory/v1/offer/{offer_id}/publish", token, {})
            listing = pub.get("listingId", "")
            for w in pub.get("warnings", []):
                print(f"    warning: {w.get('message')}")
            print(f"  LISTED   {sku:24} https://www.ebay.com/itm/{listing}")
            results.append([sku, r["title"], r["price"], offer_id, listing, "LISTED", ""])
        except EbayError as e:
            print(f"  FAILED   {sku:24} {e}")
            results.append([sku, r["title"], r["price"], "", "", "FAILED", str(e)])

    new = not RESULTS_OUT.exists()
    with RESULTS_OUT.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["SKU", "Title", "Price", "Offer ID", "Listing ID", "Result", "Error"])
        w.writerows(results)
    ok = sum(1 for x in results if x[5] == "LISTED")
    skipped = sum(1 for x in results if x[5] == "SKIPPED")
    print(f"\n{ok} listed, {skipped} skipped, {len(results) - ok - skipped} failed. Details: {RESULTS_OUT.name}")


# ================================================================== auth / policies
def do_auth(ebay):
    runame = env("EBAY_RUNAME")
    url = f"{AUTH}/oauth2/authorize?" + urllib.parse.urlencode({
        "client_id": env("EBAY_CLIENT_ID"), "redirect_uri": runame,
        "response_type": "code", "scope": " ".join(SCOPES_USER)})
    print("1) Open this link, sign in with your eBay SELLER account and click Agree:\n")
    print(url)
    print("\n2) After agreeing you land on a page whose address contains ?code=...")
    back = input("   Paste that whole address (or just the code) here: ").strip()
    code = urllib.parse.parse_qs(urllib.parse.urlparse(back).query).get("code", [back])[0]
    tok = ebay._token({"grant_type": "authorization_code", "code": urllib.parse.unquote(code),
                       "redirect_uri": runame})
    rt = tok["refresh_token"]
    days = int(tok.get("refresh_token_expires_in", 0)) // 86400
    envfile = HERE / ".env"
    if input(f"\nGot a refresh token (valid ~{days} days). Save it to {envfile.name}? [y/N] ").lower().startswith("y"):
        with envfile.open("a", encoding="utf-8") as f:
            f.write(f"\nEBAY_REFRESH_TOKEN={rt}\n")
        print("Saved.")
    else:
        print(f"\nAdd this line to your .env:\nEBAY_REFRESH_TOKEN={rt}")


def has_api_offer(ebay, token, sku):
    """True if the Inventory API already has an offer for this SKU (e.g. after migrate)."""
    try:
        _, found = ebay.call("GET", "/sell/inventory/v1/offer", token,
                             params={"sku": sku, "marketplace_id": MARKETPLACE})
        return bool(found.get("offers"))
    except EbayError as e:
        if e.status == 404:
            return False
        raise


def do_migrate(ebay, listing_ids):
    """Hand listings made in Seller Hub over to the Inventory API (eBay bulkMigrateListing).
    Nothing is ended or duplicated: the same listing (same item number, watchers, sales
    history) becomes manageable by this script. Requirement: the listing's Custom label
    (SKU) in Seller Hub must equal the SKU in CATALOG (e.g. HAIR-005)."""
    if not listing_ids:
        sys.exit("Usage: python ebay_bulk_all_products.py migrate <eBay item number> [more item numbers]")
    token = ebay.user_token()
    known = {i["sku"] for i in CATALOG.values()}
    _, data = ebay.call("POST", "/sell/inventory/v1/bulk_migrate_listing", token,
                        {"requests": [{"listingId": x} for x in listing_ids]})
    for resp in data.get("responses", []):
        lid = resp.get("listingId")
        if resp.get("statusCode") == 200:
            for it in resp.get("inventoryItems", []):
                sku = it.get("sku")
                note = "" if sku in known else "   <-- this SKU is not in CATALOG; set Custom label to the CATALOG SKU"
                print(f"  MIGRATED listing {lid} -> SKU {sku}, offer {it.get('offerId')}{note}")
        else:
            for e in resp.get("errors", []):
                print(f"  FAILED   listing {lid}: [{e.get('errorId')}] {e.get('longMessage') or e.get('message')}")
    print("\nNext publish of a migrated SKU UPDATES that same listing (weight, title, photos, description,\n"
          "price and quantity from the website + CATALOG). Run `plan` first to review.")


def do_policies(ebay):
    """READ-ONLY: lists the business policies you already made in Seller Hub. Never creates any."""
    token = ebay.user_token()
    lines = []
    for kind, key in (("fulfillment", "fulfillmentPolicies"), ("payment", "paymentPolicies"), ("return", "returnPolicies")):
        try:
            _, data = ebay.call("GET", f"/sell/account/v1/{kind}_policy", token, params={"marketplace_id": MARKETPLACE})
        except EbayError as e:
            print(f"{kind}: {e}\n  (Business policies must be turned on: Seller Hub > Account > Business policies)")
            continue
        pols = data.get(key, [])
        label = {"fulfillment": "SHIPPING", "payment": "PAYMENT", "return": "RETURN"}[kind]
        print(f"\n{label} policies ({len(pols)} found)  ->  EBAY_{kind.upper()}_POLICY_ID")
        for pol in pols:
            extra = ""
            if kind == "fulfillment":
                opts = pol.get("shippingOptions", [])
                svcs = [sv for o in opts for sv in o.get("shippingServices", [])]
                cost = ", ".join(sorted({o.get("costType", "") for o in opts}))
                free = any(sv.get("freeShipping") for sv in svcs)
                names = ", ".join(sv.get("shippingServiceCode", "") for sv in svcs[:2])
                extra = f"   [{cost}{', FREE shipping' if free else ''}; {names}]"
            print(f"  {pol[kind + 'PolicyId']:>14}  {pol.get('name')}{extra}")
        if len(pols) == 1:
            lines.append(f"EBAY_{kind.upper()}_POLICY_ID={pols[0][kind + 'PolicyId']}")
    if len(lines) == 3:
        print("\nYou have exactly one of each. Paste these 3 lines into .env:\n  " + "\n  ".join(lines))
    else:
        print("\nPick the ones your Crystal Hair Removal listing uses (Seller Hub > edit listing > "
              "Shipping/Payment/Returns show the policy names) and put their IDs in .env.")
    print("\nPolicies are account-wide: the same 3 IDs are used for every product this script lists.")


# ================================================================== main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="plan", choices=["plan", "publish", "auth", "policies", "migrate"])
    ap.add_argument("listing_ids", nargs="*", help="(migrate) eBay item numbers of listings made in Seller Hub")
    ap.add_argument("--source", default=SITE + "index.html")
    ap.add_argument("--only", default="")
    ap.add_argument("--allow-missing-weight", action="store_true")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--quantity", type=int, default=None,
                    help="override the quantity for the --only SKUs (e.g. 100 when relisting your book)")
    args = ap.parse_args()
    if args.quantity is not None:
        if not args.only:
            sys.exit("--quantity needs --only SKU (it changes the quantity of specific items).")
        if args.quantity < 1:
            sys.exit("Quantity 0 would end or relist the listing, not pause it.\n"
                     "To take a listing off eBay but keep it ready, run:  python pause_book.py pause")

    envfile = load_env()
    ebay = Ebay()
    print(f"eBay PRODUCTION ({API})   .env: {envfile or 'not found'}")
    if args.command == "auth":
        return do_auth(ebay)
    if args.command == "policies":
        return do_policies(ebay)
    if args.command == "migrate":
        return do_migrate(ebay, args.listing_ids)
    if args.command == "publish" and args.offline:
        sys.exit("--offline cannot be used with publish.")
    if not args.offline and not (os.environ.get("EBAY_CLIENT_ID") and os.environ.get("EBAY_CERT_ID")):
        print("No EBAY_CLIENT_ID/EBAY_CERT_ID yet -> planning offline (category checks skipped).")
        args.offline = True

    rows = build_plan(args, ebay)
    print_plan(rows)
    print(f"\nCSV written: {write_csv(rows)}")
    if args.command == "publish":
        publish(args, ebay, rows)
    else:
        print("\nDry run only - nothing was created on eBay. When the READY list looks right:\n"
              "  python ebay_bulk_all_products.py publish --only LAST-BUS-978    (try one first)\n"
              "  python ebay_bulk_all_products.py publish")


if __name__ == "__main__":
    main()

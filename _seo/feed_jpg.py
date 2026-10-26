#!/usr/bin/env python3
"""Make a JPEG copy of a product WebP for the Facebook/Meta catalog (Meta accepts only JPEG/PNG).

    python3 _seo/feed_jpg.py images/foo-1000.webp images/feed/foo.jpg

Called by build_seo.js for photos that don't have a copy yet. Keeps the size (no upscaling,
no cropping); pads to at least 500x500 on white because Meta rejects smaller images.
Output stays under 300 KB.
"""
import sys
from pathlib import Path
from PIL import Image

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
im = Image.open(src).convert("RGB")
if min(im.size) < 500:
    side = max(500, *im.size)
    canvas = Image.new("RGB", (side, side), "white")
    canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    im = canvas
dst.parent.mkdir(parents=True, exist_ok=True)
for q in (85, 78, 70, 60, 50):
    im.save(dst, "JPEG", quality=q, optimize=True, progressive=True)
    if dst.stat().st_size < 300_000:
        break

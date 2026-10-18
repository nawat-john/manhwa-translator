"""Stage 1: split the double-page scans into single pages.

Every scan in the source folder is a 2140x1510 two-page spread read
right-to-left, verified against the printed page numbers:

    0004.png -> right half = p140, left half = p141
    0005.png -> right half = p142, left half = p143
    0006.png -> right half = p144, left half = p145

So each spread yields two output pages in reading order: right first, then
left.  Output names are a zero-padded running index, which makes lexicographic
sort equal reading order for every later stage (the translator's batch mode and
the PDF build both rely on this).

A sidecar ``page_map.json`` keeps the provenance of each output page so a bad
page can be traced back to its spread and half.

Idempotent: pages already present are left alone unless --force is passed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# A spread wider than this ratio is treated as two pages side by side.
SPREAD_ASPECT_MIN = 1.15

# Column-ink profiling showed the gutter is a blank band 82-140 px wide sitting
# dead on width//2 on every spread checked, so the split is a plain midpoint cut.
# This only measures how much clear space surrounds that cut, to flag spreads
# where art bleeds across the fold and the split will land on artwork.
GUTTER_PROBE = 12       # px either side of the cut to inspect
INK_LEVEL = 200         # grey darker than this counts as ink


def gutter_clearance(img: Image.Image, x: int) -> int:
    """How many of the columns around the cut are free of ink. 0 = full-bleed."""
    a = np.asarray(img.convert("L"), dtype=np.uint8)
    lo, hi = max(0, x - GUTTER_PROBE), min(a.shape[1], x + GUTTER_PROBE)
    return int((~(a[:, lo:hi] < INK_LEVEL).any(axis=0)).sum())


def split(src_dir: Path, out_dir: Path, force: bool) -> dict:
    scans = sorted(src_dir.glob("*.png"))
    if not scans:
        sys.exit(f"no .png found in {src_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)
    page_map: dict[str, dict] = {}
    index = 0
    written = skipped = 0
    bleeding: list[str] = []

    for scan in scans:
        with Image.open(scan) as im:
            im.load()
            w, h = im.size
            is_spread = (w / h) >= SPREAD_ASPECT_MIN

            if is_spread:
                x = w // 2
                clear = gutter_clearance(im, x)
                if clear == 0:
                    bleeding.append(scan.name)
                # Reading order: right half of the sheet is the earlier page.
                halves = [("right", im.crop((x, 0, w, h))),
                          ("left", im.crop((0, 0, x, h)))]
            else:
                x, clear = None, None
                halves = [("full", im.copy())]

            for half, page_img in halves:
                index += 1
                name = f"{index:04d}.png"
                dest = out_dir / name
                page_map[name] = {
                    "source": scan.name,
                    "half": half,
                    "split_x": x,
                    "gutter_clear_cols": clear,
                    "size": list(page_img.size),
                }
                if dest.exists() and not force:
                    skipped += 1
                else:
                    page_img.save(dest, "PNG", optimize=True)
                    written += 1
                page_img.close()

    map_path = out_dir.parent / "page_map.json"
    map_path.write_text(json.dumps(page_map, indent=2), encoding="utf-8")

    print(f"spreads read : {len(scans)}")
    print(f"pages total  : {index}")
    print(f"  written    : {written}")
    print(f"  skipped    : {skipped} (already present; use --force to redo)")
    print(f"page map     : {map_path}")
    if bleeding:
        print(f"\nart crosses the fold on {len(bleeding)} spread(s); the cut lands on "
              f"artwork there, which is correct but worth an eye:")
        print("  " + ", ".join(bleeding))
    return page_map


def main() -> None:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=Path(r"D:\Code\hanaori-san-scrape\vol1"),
                    help="folder of double-page scans")
    ap.add_argument("--out", type=Path, default=here / "work" / "pages",
                    help="folder to write single pages into")
    ap.add_argument("--force", action="store_true", help="rewrite pages that already exist")
    args = ap.parse_args()

    split(args.src.resolve(), args.out.resolve(), args.force)


if __name__ == "__main__":
    main()

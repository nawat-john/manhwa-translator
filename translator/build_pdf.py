"""Stage 3: assemble the translated pages into a single PDF.

The PDF is always complete.  Any page that never made it through the translator
- quarantined, or still pending because the run was stopped early - is included
as the untouched Japanese original rather than left out, so page numbers and
reading order stay intact.  Which pages those were is printed at the end and
recorded in ``output/build-report.json``.

Pages are re-encoded to JPEG on disk first and then streamed into the PDF by
img2pdf, instead of holding ~390 decoded images in memory at once.  The JPEG
cache is reused across runs, so rebuilding after translating a few more pages
only re-encodes what changed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
WORK = HERE / "work"
PAGES = WORK / "pages"
OUT = WORK / "out"
JPEGS = WORK / "pdf-jpegs"
STATE_PATH = WORK / "state.json"
PAGE_MAP = WORK / "page_map.json"

Image.MAX_IMAGE_PIXELS = None


def is_greyscale(img: Image.Image, tolerance: int = 12) -> bool:
    """True if the image carries no meaningful colour, checked on a thumbnail."""
    if img.mode in ("L", "1"):
        return True
    probe = img.convert("RGB").copy()
    probe.thumbnail((160, 160))
    return max(abs(r - g) + abs(g - b) for r, g, b in probe.getdata()) <= tolerance


def encode_page(src: Path, dst: Path, dpi: int, quality: int, force: bool) -> None:
    if dst.exists() and not force and dst.stat().st_mtime >= src.stat().st_mtime:
        return
    with Image.open(src) as im:
        im.load()
        im = im.convert("L") if is_greyscale(im) else im.convert("RGB")
        im.save(dst, "JPEG", quality=quality, optimize=True,
                progressive=True, dpi=(dpi, dpi))


def build(args) -> int:
    if not PAGES.exists() or not any(PAGES.glob("*.png")):
        sys.exit(f"no split pages in {PAGES}\nrun split_pages.py first")

    try:
        import img2pdf
    except ImportError:
        sys.exit("img2pdf is not installed in this venv\n"
                 "  .venv\\Scripts\\pip.exe install img2pdf")

    page_map = json.loads(PAGE_MAP.read_text(encoding="utf-8")) if PAGE_MAP.exists() else {}
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {"pages": {}}

    JPEGS.mkdir(parents=True, exist_ok=True)
    names = sorted(p.name for p in PAGES.glob("*.png"))

    jpeg_paths: list[str] = []
    fallbacks: list[dict] = []

    for i, name in enumerate(names, 1):
        translated = OUT / name
        if translated.exists():
            src, kind = translated, "translated"
        else:
            src, kind = PAGES / name, "original"
            entry = state.get("pages", {}).get(name, {})
            fallbacks.append({
                "page": name,
                "status": entry.get("status", "unknown"),
                "reason": entry.get("quarantine_reason") or "not translated yet",
                "spread": page_map.get(name, {}).get("source"),
                "half": page_map.get(name, {}).get("half"),
            })

        dst = JPEGS / f"{Path(name).stem}.jpg"
        encode_page(src, dst, args.dpi, args.quality, args.force)
        jpeg_paths.append(str(dst))

        if i % 25 == 0 or i == len(names):
            print(f"  encoded {i}/{len(names)}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    print(f"\nwriting {args.out} ...")
    with args.out.open("wb") as fh:
        fh.write(img2pdf.convert(jpeg_paths, title=args.title))

    report = {
        "built_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "pdf": str(args.out),
        "pages_total": len(names),
        "pages_translated": len(names) - len(fallbacks),
        "pages_fallback_to_original": len(fallbacks),
        "dpi": args.dpi,
        "jpeg_quality": args.quality,
        "fallbacks": fallbacks,
    }
    report_path = args.out.parent / "build-report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    size_mb = args.out.stat().st_size / 1024 / 1024
    print(f"\n{'=' * 60}")
    print(f"pdf         : {args.out}  ({size_mb:.1f} MB)")
    print(f"pages       : {len(names)}")
    print(f"translated  : {len(names) - len(fallbacks)}")
    print(f"original    : {len(fallbacks)}")
    for f in fallbacks[:20]:
        print(f"    {f['page']}  ({f['spread']} {f['half']})  {f['status']}: {f['reason']}")
    if len(fallbacks) > 20:
        print(f"    ... and {len(fallbacks) - 20} more, see {report_path}")
    print(f"report      : {report_path}")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=HERE / "output" / "hanaori-san-vol1-en.pdf")
    ap.add_argument("--title", default="Hanaori-san wa Tensei Shitemo Kenka ga Shitai - vol. 1 (EN)")
    ap.add_argument("--dpi", type=int, default=150,
                    help="page scale; 150 puts a 1070x1510 page at about 7.1 x 10.1 in (default 150)")
    ap.add_argument("--quality", type=int, default=88, help="JPEG quality (default 88)")
    ap.add_argument("--force", action="store_true", help="re-encode every page even if cached")
    args = ap.parse_args()
    sys.exit(build(args))


if __name__ == "__main__":
    main()

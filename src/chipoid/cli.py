"""Command-line entry point.

Usage:
    chipoid run --config configs/default.yaml

    # Ad-hoc extraction outside of a batch — the pipeline `run` does this
    # automatically when extract_channels.enabled=true. The data_root is
    # treated as read-only by `run`; this standalone subcommand also lets
    # the caller pick any --out-dir (we recommend somewhere under output/,
    # not under data/).
    chipoid extract --raw <multipage.tif> --image-id <id> --out-dir <output/<id>/> \
                    --markers green,red --pages brightfield=0,green=1,red=2
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .extract import extract_one
from .pipeline import run_batch


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="chipoid")
    sub = ap.add_subparsers(dest="command", required=True)

    # `chipoid run`
    p_run = sub.add_parser("run", help="Run the full batch pipeline from a config")
    p_run.add_argument("--config", required=True, type=Path,
                       help="Path to YAML config")

    # `chipoid extract` — standalone one-off extraction (for ad-hoc preprocessing)
    p_ex = sub.add_parser("extract", help="Extract pages from one multi-page TIFF")
    p_ex.add_argument("--raw", required=True, type=Path)
    p_ex.add_argument("--image-id", required=True)
    p_ex.add_argument("--out-dir", required=True, type=Path)
    p_ex.add_argument("--markers", required=True,
                      help="Comma-separated marker names, e.g. green,red")
    p_ex.add_argument("--pages", required=True,
                      help="Comma-separated channel=page pairs, e.g. "
                           "brightfield=0,green=1,red=2")
    p_ex.add_argument("--no-bf-stretch", action="store_true",
                      help="Skip the BF 8-bit percentile stretch (keep native dtype)")

    args = ap.parse_args(argv)

    if args.command == "run":
        result = run_batch(args.config)
        print(f"\ndone. {result['n_success']}/{result['n_images']} images succeeded; "
              f"output in {result['out_root']}")
        return 0 if result["n_failed"] == 0 else 1

    if args.command == "extract":
        markers = [m.strip() for m in args.markers.split(",") if m.strip()]
        pages = {}
        for pair in args.pages.split(","):
            k, v = pair.split("=", 1)
            pages[k.strip()] = int(v)
        written = extract_one(
            raw_path=args.raw, image_id=args.image_id, out_dir=args.out_dir,
            pages=pages, markers=markers,
            brightfield_to_8bit=not args.no_bf_stretch,
        )
        for k, p in written.items():
            print(f"  {k}: {p}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Pre-compute Gemini "full" dimensioning for the built-in samples so public
visitors get AI results with zero API calls.

Run from backend/ (needs GEMINI_API_KEY in backend/.env):
    python -m scripts.precompute_annotations                # all view combos, both samples
    python -m scripts.precompute_annotations --only stepped_shaft --views front,top,right
    python -m scripts.precompute_annotations --force         # overwrite existing files

Writes backend/samples/annotations/<sample>/full__<views>.json (commit these).
"""
from __future__ import annotations

import argparse
import itertools
import sys
import time

from app.annotation.service import dump_precomputed, precomputed_path, run_ai
from app.core.config import settings
from app.pipeline import analyze_part
from samples import SAMPLE_PARTS, sample_path

OTHERS = ("top", "bottom", "left", "right", "rear")


def all_combos() -> list[list[str]]:
    combos = [["front"]]
    for n in (1, 2):
        combos += [["front", *c] for c in itertools.combinations(OTHERS, n)]
    return combos


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="sample id")
    ap.add_argument("--views", help="comma list (default: all 16 combos with front)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--delay", type=float, default=7.0, help="seconds between calls (free-tier RPM)")
    args = ap.parse_args()

    if not settings.gemini_api_key:
        print("GEMINI_API_KEY is not set (backend/.env)")
        return 2

    combos = [args.views.split(",")] if args.views else all_combos()
    ok = fail = skipped = 0
    for sid in SAMPLE_PARTS:
        if args.only and sid != args.only:
            continue
        analysis = analyze_part(sample_path(sid))
        for views in combos:
            if precomputed_path(sid, views).exists() and not args.force:
                skipped += 1
                continue
            t0 = time.perf_counter()
            try:
                result = run_ai(analysis, views)
            except Exception as exc:
                fail += 1
                print(f"[fail] {sid:<17} {','.join(views):<22} {str(exc)[:140]}", flush=True)
            else:
                ok += 1
                path = dump_precomputed(sid, result)
                n_lin = sum(d.type == "linear" for d in result.dimensions)
                print(f"[ok]   {sid:<17} {','.join(views):<22} {len(result.dimensions):>2} dims "
                      f"({n_lin} linear), {result.rejected} rejected, {time.perf_counter() - t0:.1f}s -> {path.name}",
                      flush=True)
            time.sleep(args.delay)
    print(f"\n{ok} written, {skipped} skipped (exist), {fail} failed")
    return 1 if fail and not ok else 0


if __name__ == "__main__":
    sys.exit(main())

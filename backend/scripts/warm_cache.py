"""Pre-analyse the built-in samples into CACHE_DIR at Docker build time.

Free hosts (Render: 0.1 vCPU, disk wiped on every spin-down) would otherwise
re-run import + hidden-line projection for every sample after each wake. Baking
the results into the image makes the one-click samples instant.

    python -m scripts.warm_cache
"""
from __future__ import annotations

import sys
import time

from app.api.routes import load_sample, store
from samples import SAMPLE_PARTS


def main() -> int:
    t0 = time.perf_counter()
    for sample_id in SAMPLE_PARTS:
        entry = load_sample(sample_id)
        print(f"[warm] {sample_id:<17} -> {entry.directory}", flush=True)
    print(f"[warm] {len(SAMPLE_PARTS)} samples cached in {store.root} ({time.perf_counter() - t0:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

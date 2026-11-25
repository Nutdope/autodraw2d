"""High-level orchestration: STEP file -> PartAnalysis (geometry + projections).

Split on purpose into two stages:
  1. ``analyze_part``   – expensive OCC work (import, features, HLR). Cache per file.
  2. ``compute_layout`` – cheap pure-Python sheet placement. Re-run on every UI change.
"""
from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Iterable, Optional

from .geometry import ALL_VIEWS, VIEW_DEFS
from .geometry.features import analyze_geometry
from .geometry.loader import load_step
from .geometry.mesh import export_preview_stl
from .geometry.models import PartAnalysis
from .geometry.projection import project_view


def analyze_part(
    step_path: str | Path,
    views: Iterable[str] = ALL_VIEWS,
    mesh_out: Optional[str | Path] = None,
) -> PartAnalysis:
    timings: dict[str, float] = {}

    def lap(key: str, t0: float) -> None:
        timings[key] = round((time.perf_counter() - t0) * 1000, 1)

    t = time.perf_counter()
    shape = load_step(step_path)
    lap("import", t)

    t = time.perf_counter()
    geometry = analyze_geometry(shape.wrapped)
    lap("features", t)

    diag = math.sqrt(sum(c * c for c in geometry.size))
    projections = {}
    t = time.perf_counter()
    for name in views:
        if name not in VIEW_DEFS:
            raise ValueError(f"unknown view '{name}'")
        projections[name] = project_view(shape.wrapped, VIEW_DEFS[name], geometry.features, diag)
    lap("projection", t)

    mesh_file = None
    if mesh_out is not None:
        t = time.perf_counter()
        mesh_file = str(export_preview_stl(shape, mesh_out, max(geometry.size)))
        lap("mesh", t)

    return PartAnalysis(
        part_name=Path(step_path).stem,
        geometry=geometry,
        views=projections,
        mesh_file=mesh_file,
        timings_ms=timings,
    )

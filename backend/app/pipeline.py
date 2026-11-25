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
from .geometry.orientation import Orientation, apply
from .geometry.mesh import export_preview_stl
from .geometry.models import PartAnalysis, SectionProjection
from .geometry.section import auto_depth, section_view
from .geometry.projection import project_view


def load_oriented(step_path, orientation: Optional[Orientation] = None, max_faces=None, max_solids=None):
    shape = load_step(step_path, max_faces=max_faces, max_solids=max_solids)
    if orientation is not None and not orientation.is_identity:
        from build123d.topology import downcast

        shape = type(shape)(downcast(apply(shape.wrapped, orientation)))
    return shape


def compute_section(step_path, analysis: PartAnalysis, view: str, depth: Optional[float],
                    orientation: Optional[Orientation] = None) -> SectionProjection:
    """Section of an analysed part: ``depth`` mm behind the face nearest the viewer
    (None = through the most hole axes)."""
    vd = VIEW_DEFS[view]
    g = analysis.geometry
    if depth is None:
        depth = auto_depth(g, vd)
    shape = load_oriented(step_path, orientation)
    diag = math.sqrt(sum(c * c for c in g.size))
    return section_view(shape.wrapped, g, vd, analysis.views[view], depth, diag)


def analyze_part(
    step_path: str | Path,
    views: Iterable[str] = ALL_VIEWS,
    mesh_out: Optional[str | Path] = None,
    max_faces: Optional[int] = None,
    max_solids: Optional[int] = None,
    orientation: Optional[Orientation] = None,
) -> PartAnalysis:
    timings: dict[str, float] = {}

    def lap(key: str, t0: float) -> None:
        timings[key] = round((time.perf_counter() - t0) * 1000, 1)

    t = time.perf_counter()
    shape = load_oriented(step_path, orientation, max_faces=max_faces, max_solids=max_solids)
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

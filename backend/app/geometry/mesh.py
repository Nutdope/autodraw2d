"""Tessellated preview mesh for the frontend 3D widget."""
from __future__ import annotations

from pathlib import Path

from build123d import Shape, export_stl


def export_preview_stl(shape: Shape, out_path: str | Path, part_size: float) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tolerance = max(0.01, part_size * 1e-3)  # chordal error, scales with part size
    export_stl(shape, str(out_path), tolerance=tolerance, angular_tolerance=0.2)
    return out_path

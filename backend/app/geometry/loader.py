"""STEP import + basic validation."""
from __future__ import annotations

from pathlib import Path

from build123d import Shape, import_step
from OCP.TopAbs import TopAbs_ShapeEnum

from .topo import iter_shapes

MAX_STEP_BYTES = 25 * 1024 * 1024  # public-hosting guard rail


class StepImportError(ValueError):
    pass


def load_step(path: str | Path) -> Shape:
    path = Path(path)
    if not path.is_file():
        raise StepImportError(f"file not found: {path}")
    if path.suffix.lower() not in (".step", ".stp"):
        raise StepImportError("only .step / .stp files are supported")
    if path.stat().st_size > MAX_STEP_BYTES:
        raise StepImportError(f"file larger than {MAX_STEP_BYTES // (1024 * 1024)} MB")

    try:
        shape = import_step(str(path))
    except Exception as exc:  # OCC raises a variety of exception types
        raise StepImportError(f"could not read STEP file: {exc}") from exc

    if shape is None or shape.wrapped is None or shape.wrapped.IsNull():
        raise StepImportError("STEP file contains no geometry")
    if not any(True for _ in iter_shapes(shape.wrapped, TopAbs_ShapeEnum.TopAbs_SOLID)):
        raise StepImportError("STEP file contains no solid bodies (surfaces/wireframes only)")
    return shape

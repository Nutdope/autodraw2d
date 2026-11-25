"""STEP import + basic validation."""
from __future__ import annotations

from pathlib import Path

from build123d import Shape, import_step
from OCP.TopAbs import TopAbs_ShapeEnum

from .topo import iter_shapes

MAX_STEP_BYTES = 25 * 1024 * 1024  # public-hosting guard rail


class StepImportError(ValueError):
    pass


class PartTooComplexError(StepImportError):
    """Raised before hidden-line projection, whose memory use grows with face count."""


def load_step(path: str | Path, max_faces: int | None = None, max_solids: int | None = None) -> Shape:
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
    solids = sum(1 for _ in iter_shapes(shape.wrapped, TopAbs_ShapeEnum.TopAbs_SOLID))
    if not solids:
        raise StepImportError("STEP file contains no solid bodies (surfaces/wireframes only)")
    if max_solids is not None and solids > max_solids:
        raise PartTooComplexError(
            f"Part too complex for this demo server: {solids} bodies (limit {max_solids}). "
            "Upload a single part rather than an assembly."
        )
    if max_faces is not None:
        faces = sum(1 for _ in iter_shapes(shape.wrapped, TopAbs_ShapeEnum.TopAbs_FACE))
        if faces > max_faces:
            raise PartTooComplexError(
                f"Part too complex for this demo server: {faces} faces (limit {max_faces}). "
                "Try a simpler part or remove cosmetic detail (threads, text, knurling)."
            )
    return shape

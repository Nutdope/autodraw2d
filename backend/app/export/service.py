"""Export orchestration: (part, user state) -> file bytes."""
from __future__ import annotations

import re

from ..geometry.models import PartAnalysis
from ..layout import compute_layout
from .builder import build_sheet
from .models import ExportRequest
from .writers import to_dxf, to_pdf, to_svg

MEDIA = {"svg": "image/svg+xml", "dxf": "application/dxf", "pdf": "application/pdf"}


def export_filename(req: ExportRequest, fallback: str) -> str:
    base = req.title.drawingNumber or req.title.partName or fallback
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("_") or "drawing"
    return f"{slug}.{req.format}"


def export_sheet(analysis: PartAnalysis, req: ExportRequest) -> tuple[bytes, str]:
    """Returns (file bytes, media type). The layout is recomputed server-side from the
    same SheetConfig the UI used, so placement is identical to the screen."""
    layout = compute_layout(analysis.views, req.sheet)
    model = build_sheet(analysis, layout, req)
    title = req.title.partName or analysis.part_name
    if req.format == "dxf":
        return to_dxf(model), MEDIA["dxf"]
    svg = to_svg(model, title)
    if req.format == "svg":
        return svg.encode("utf-8"), MEDIA["svg"]
    return to_pdf(svg), MEDIA["pdf"]

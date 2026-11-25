"""Sheet configuration (validated input) and layout result schemas.

Sheet coordinates: millimetres on paper, origin top-left of the page, y DOWN.
A view is placed with the SVG transform
    translate(x_offset, y_offset) scale(scale)
applied to its view-local geometry (see app.geometry.models).
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, field_validator

from ..geometry.views import OrthoViewName

PageFormat = Literal["A4", "A3", "A2", "A1"]
Orientation = Literal["landscape", "portrait"]
DrawingStandard = Literal["ISO", "ANSI"]

MAX_ORTHO_VIEWS = 3
_SCALE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\s*$")


class SheetConfig(BaseModel):
    page_format: PageFormat = "A3"
    orientation: Orientation = "landscape"
    standard: DrawingStandard = "ISO"
    ortho_views: list[OrthoViewName] = ["front", "top", "right"]
    show_isometric: bool = True
    scale: str = "auto"  # "auto" or "N:M", e.g. "1:2"

    @field_validator("ortho_views")
    @classmethod
    def _check_views(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("duplicate orthographic views")
        if len(v) > MAX_ORTHO_VIEWS:
            raise ValueError(f"at most {MAX_ORTHO_VIEWS} orthographic views may be active")
        if v and "front" not in v:
            raise ValueError("the front view is the base view and must be included")
        return v

    @field_validator("scale")
    @classmethod
    def _check_scale(cls, v: str) -> str:
        if v.strip().lower() == "auto":
            return "auto"
        m = _SCALE_RE.match(v)
        if not m or float(m.group(1)) <= 0 or float(m.group(2)) <= 0:
            raise ValueError("scale must be 'auto' or of the form 'N:M' (e.g. '1:2')")
        return f"{m.group(1)}:{m.group(2)}"

    def scale_factor(self) -> Optional[float]:
        if self.scale == "auto":
            return None
        a, b = self.scale.split(":")
        return float(a) / float(b)


class Rect(BaseModel):
    x: float
    y: float
    w: float
    h: float


class Zones(BaseModel):
    columns: list[str]  # "1".."n", left -> right
    rows: list[str]  # "A".., top -> bottom
    col_edges: list[float]  # x positions of zone boundaries along the frame
    row_edges: list[float]


class ViewPlacement(BaseModel):
    view: str
    scale: float
    scale_label: str
    x_offset: float
    y_offset: float
    rect: Rect  # paper footprint of the view geometry (without dimensions)
    grid_cell: Optional[tuple[int, int]] = None  # (col, row) relative to front; None = iso


class SheetLayout(BaseModel):
    page_format: PageFormat
    orientation: Orientation
    standard: DrawingStandard
    projection_method: Literal["first_angle", "third_angle"]
    units: Literal["mm"] = "mm"
    page_width: float
    page_height: float
    frame: Rect
    title_block: Rect
    zones: Zones
    view_clearance: float
    scale: float
    scale_label: str
    auto_scale: bool
    placements: list[ViewPlacement]
    fits: bool
    warnings: list[str] = []

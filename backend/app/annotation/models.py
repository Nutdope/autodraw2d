"""Dimension primitives shared by the deterministic dimensioner, the AI layer,
the frontend and (Milestone 4) the exporters.

Coordinates: view-local model mm (origin top-left of the view bbox, y DOWN),
i.e. the same space as ViewProjection geometry. Paper quantities
(offsets, leader lengths, text shifts) are in sheet mm and do not scale.

Linear dimension placement
--------------------------
* horizontal: offset_mm > 0 puts the dimension line ABOVE, < 0 BELOW.
* vertical:   offset_mm > 0 puts the dimension line to the RIGHT, < 0 LEFT.
* offset_from = "edge":   measured from the view bbox edge on that side
  offset_from = "points": measured from the outermost of the two points
  (offset 0 + "points" draws the line straight between the points, e.g. a
  diameter across a shaft).

Circle dimensions
-----------------
leader_angle_deg: paper convention, CCW from +x with y UP. The arrow touches
the circle at that angle; ``inside=True`` runs the leader back through the
centre (used for concave fillets whose centre lies in free space).
"""
from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

from ..geometry.views import OrthoViewName
from ..layout.models import MAX_ORTHO_VIEWS

DimensionMode = Literal["none", "overall", "key", "full"]
AnnotationSource = Literal["deterministic", "ai", "ai_cached", "precomputed"]


class LinearDim(BaseModel):
    type: Literal["linear"] = "linear"
    id: str
    view: str
    x1: float
    y1: float
    x2: float
    y2: float
    orientation: Literal["horizontal", "vertical"]
    offset_mm: float
    offset_from: Literal["edge", "points"] = "edge"
    value_mm: float
    prefix: Literal["", "Ø"] = ""
    tolerance_text: Optional[str] = None
    text_shift_mm: float = 0.0
    feature_ids: list[str] = []  # features this dimension describes (coverage checks)


class CircleDim(BaseModel):
    """Leader callout. diameter/radius: arrow on a circle/arc of `radius`;
    leader: arrow on the point (cx, cy) itself (radius 0) — chamfers, slot depth."""

    type: Literal["diameter", "radius", "leader"]
    id: str
    view: str
    cx: float
    cy: float
    radius: float
    leader_angle_deg: float
    leader_len_mm: float = 10.0
    inside: bool = False
    label_text: str
    feature_ids: list[str] = []


Dimension = Annotated[Union[LinearDim, CircleDim], Field(discriminator="type")]


class AnnotationSet(BaseModel):
    mode: DimensionMode
    views: list[str]
    source: AnnotationSource
    dimensions: list[Dimension]
    notes: list[str]
    fallback_reason: Optional[str] = None  # why AI wasn't used (UI shows a subtle toast)
    model: Optional[str] = None
    rejected: int = 0  # AI primitives dropped by geometric validation


class AnnotateRequest(BaseModel):
    mode: DimensionMode = "key"
    ortho_views: list[OrthoViewName] = ["front", "top", "right"]
    use_ai: bool = False  # only an explicit "Auto-Dimension (AI)" click spends quota
    tolerance: str = "ISO 2768-m"

    @field_validator("ortho_views")
    @classmethod
    def _check(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v) or len(v) > MAX_ORTHO_VIEWS:
            raise ValueError(f"1–{MAX_ORTHO_VIEWS} distinct orthographic views required")
        if v and "front" not in v:
            raise ValueError("the front view is the base view and must be included")
        return v

"""Pydantic schemas for deterministic geometry results.

These are the exact numbers the rest of the system (layout, AI annotator,
exporters, frontend) consumes. Nothing downstream may invent geometry.

Coordinate conventions
----------------------
* 3D values: world millimetres, Z up, part front faces -Y.
* ``ViewProjection.bbox``: projected 2D coords (y-UP), origin = world origin.
* Everything else inside a ViewProjection (primitives, svg paths, center marks,
  centerlines) is **view-local SVG space**: millimetres at 1:1, origin at the
  top-left of the view's 2D bounding box, y pointing DOWN.
  local_x = x - bbox.xmin,  local_y = bbox.ymax - y
"""
from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field

Point2 = tuple[float, float]
Vec3 = tuple[float, float, float]

FeatureKind = Literal["hole", "boss", "concave_arc", "convex_arc"]


# ---------------------------------------------------------------------------
# 3D features
# ---------------------------------------------------------------------------
class CylinderFeature(BaseModel):
    id: str
    kind: FeatureKind  # hole = internal full cylinder, boss = external (shaft / pin)
    radius: float
    diameter: float
    axis: Vec3  # canonical unit direction
    axis_aligned: Optional[Literal["X", "Y", "Z"]] = None
    start: Vec3  # axis point at one end of the cylindrical extent
    end: Vec3
    center: Vec3
    length: float
    angular_span_deg: float  # 360 for full cylinders, <360 for fillets/rounds
    through: Optional[bool] = None  # holes only
    face_count: int = 1


class FeatureGroup(BaseModel):
    """Identical features collapsed into a single callout (e.g. '4x Ø8.0 THRU')."""

    kind: FeatureKind
    label: str
    count: int
    diameter: Optional[float] = None
    radius: Optional[float] = None
    axis: Vec3
    through: Optional[bool] = None
    feature_ids: list[str]


class PartGeometry(BaseModel):
    bbox_min: Vec3
    bbox_max: Vec3
    size: Vec3  # (dx, dy, dz)
    volume: float
    surface_area: float
    center_of_mass: Vec3
    solid_count: int
    face_count: int
    features: list[CylinderFeature]
    feature_groups: list[FeatureGroup]


# ---------------------------------------------------------------------------
# 2D projection primitives (view-local SVG space, see module docstring)
# ---------------------------------------------------------------------------
class LinePrim(BaseModel):
    type: Literal["line"] = "line"
    p0: Point2
    p1: Point2


class ArcPrim(BaseModel):
    """Circular arc from p0 to p1 with SVG arc-flag semantics (y-down)."""

    type: Literal["arc"] = "arc"
    c: Point2
    r: float
    p0: Point2
    p1: Point2
    large: int
    sweep: int


class CirclePrim(BaseModel):
    type: Literal["circle"] = "circle"
    c: Point2
    r: float


class PolylinePrim(BaseModel):
    type: Literal["polyline"] = "polyline"
    pts: list[Point2]


Primitive = Annotated[
    Union[LinePrim, ArcPrim, CirclePrim, PolylinePrim], Field(discriminator="type")
]


class EdgeLayer(BaseModel):
    primitives: list[Primitive] = []
    svg_path: str = ""


class CenterMark(BaseModel):
    cx: float
    cy: float
    r: float
    feature_ids: list[str]


class Centerline(BaseModel):
    p0: Point2
    p1: Point2
    feature_ids: list[str]


class ArcMark(BaseModel):
    """A fillet / round seen as a true arc in this view (radius callout target)."""

    cx: float
    cy: float
    r: float
    feature_id: str
    concave: bool
    mid_angle_deg: float  # paper convention: CCW from +x with y UP


class ViewProjection(BaseModel):
    name: str
    is_isometric: bool
    view_dir: Vec3  # toward the viewer
    x_dir: Vec3
    y_dir: Vec3
    bbox: tuple[float, float, float, float]  # (xmin, ymin, xmax, ymax), projected y-up
    width: float
    height: float
    visible: EdgeLayer  # sharp + silhouette edges
    hidden: EdgeLayer
    tangent: EdgeLayer  # smooth (G1) edges, visible
    tangent_hidden: EdgeLayer
    center_marks: list[CenterMark]
    centerlines: list[Centerline]
    arc_marks: list[ArcMark] = []
    compute_ms: float


class PartAnalysis(BaseModel):
    part_name: str
    geometry: PartGeometry
    views: dict[str, ViewProjection]
    mesh_file: Optional[str] = None
    timings_ms: dict[str, float] = {}

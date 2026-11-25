"""API response schemas (lean versions of the internal models)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from ..geometry.models import Centerline, CenterMark, PartGeometry, Vec3
from ..geometry.orientation import Orientation
from ..services.part_store import PartEntry


class EdgeLayerOut(BaseModel):
    svg_path: str


class ViewOut(BaseModel):
    """ViewProjection without the raw primitives (those stay server-side for DXF)."""

    name: str
    is_isometric: bool
    view_dir: Vec3
    bbox: tuple[float, float, float, float]
    width: float
    height: float
    visible: EdgeLayerOut
    hidden: EdgeLayerOut
    tangent: EdgeLayerOut
    tangent_hidden: EdgeLayerOut
    center_marks: list[CenterMark]
    centerlines: list[Centerline]


class SampleOut(BaseModel):
    id: str
    name: str
    description: str
    default_material: str


class PartOut(BaseModel):
    part_id: str
    name: str
    source: Literal["sample", "upload"]
    sample_id: Optional[str]
    default_material: Optional[str]
    geometry: PartGeometry
    views: dict[str, ViewOut]
    mesh_url: str
    timings_ms: dict[str, float]
    orientation: Orientation


def part_out(entry: PartEntry, default_material: Optional[str] = None) -> PartOut:
    a = entry.analysis
    views = {
        name: ViewOut(
            name=v.name,
            is_isometric=v.is_isometric,
            view_dir=v.view_dir,
            bbox=v.bbox,
            width=v.width,
            height=v.height,
            visible=EdgeLayerOut(svg_path=v.visible.svg_path),
            hidden=EdgeLayerOut(svg_path=v.hidden.svg_path),
            tangent=EdgeLayerOut(svg_path=v.tangent.svg_path),
            tangent_hidden=EdgeLayerOut(svg_path=v.tangent_hidden.svg_path),
            center_marks=v.center_marks,
            centerlines=v.centerlines,
        )
        for name, v in a.views.items()
    }
    return PartOut(
        part_id=entry.part_id,
        name=entry.name,
        source=entry.source,  # type: ignore[arg-type]
        sample_id=entry.sample_id,
        default_material=default_material,
        geometry=a.geometry,
        views=views,
        mesh_url=f"/api/parts/{entry.part_id}/mesh.stl",
        timings_ms=a.timings_ms,
        orientation=entry.orientation,
    )

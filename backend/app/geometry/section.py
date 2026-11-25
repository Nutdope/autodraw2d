"""Full sections (ISO 128-44): cut the part with a plane and project what lies behind it.

A section *replaces* one orthographic view. The cutting plane is parallel to
that view's projection plane at ``depth`` mm behind the face nearest the
viewer. The material in front of the plane is removed, the rest goes through
the same HLR projection as a normal view, and the faces lying in the plane
are returned as closed loops for hatching.

The section reuses the uncut view's 2D frame (bbox), so its view-local
coordinates are identical: dimensions, the layout and the projection
alignment all stay valid when a view is switched to a section.
"""
from __future__ import annotations

import math
from collections import Counter

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.BRepTools import BRepTools_WireExplorer
from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_SurfaceType
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_Orientation, TopAbs_ShapeEnum
from OCP.TopoDS import TopoDS, TopoDS_Shape

from . import vec
from .models import CylinderFeature, PartGeometry, SectionProjection, ViewProjection
from .projection import project_view
from .topo import iter_shapes
from .views import ViewDef

CIRCLE_SEGMENTS = 72  # per full turn, for hatch outlines (paper-scale smooth)


def cut_axis(view: ViewDef) -> tuple[int, float]:
    """(world axis index, sign) of the view direction (toward the viewer)."""
    for i in range(3):
        if abs(abs(view.normal[i]) - 1) < 1e-9:
            return i, (1.0 if view.normal[i] > 0 else -1.0)
    raise ValueError(f"view '{view.name}' is not axis-aligned")


def plane_at(geometry: PartGeometry, view: ViewDef, depth: float) -> float:
    """World coordinate of the cutting plane `depth` mm behind the nearest face."""
    i, s = cut_axis(view)
    return geometry.bbox_max[i] - depth if s > 0 else geometry.bbox_min[i] + depth


def auto_depth(geometry: PartGeometry, view: ViewDef) -> float:
    """Cut through the most hole / boss axes that lie parallel to the plane (the
    section then shows them in true profile); else through the middle."""
    i, s = cut_axis(view)
    size = geometry.size[i]
    eps = max(1e-3, size * 1e-4)
    planes: Counter[float] = Counter()
    for f in geometry.features:
        if f.kind not in ("hole", "boss") or abs(f.axis[i]) > 1e-6:
            continue
        c = f.center[i]
        if geometry.bbox_min[i] + eps < c < geometry.bbox_max[i] - eps:
            planes[round(c, 3)] += 2 if f.kind == "hole" else 1
    if planes:
        mid = (geometry.bbox_min[i] + geometry.bbox_max[i]) / 2
        c = max(planes, key=lambda p: (planes[p], -abs(p - mid)))
    else:
        c = (geometry.bbox_min[i] + geometry.bbox_max[i]) / 2
    return round(geometry.bbox_max[i] - c if s > 0 else c - geometry.bbox_min[i], 4)


def _cut(shape: TopoDS_Shape, geometry: PartGeometry, i: int, s: float, plane: float) -> TopoDS_Shape:
    m = max(geometry.size) + 10.0
    lo = [geometry.bbox_min[k] - m for k in range(3)]
    hi = [geometry.bbox_max[k] + m for k in range(3)]
    if s > 0:
        hi[i] = plane  # viewer on +axis: keep what lies below the plane
    else:
        lo[i] = plane
    box = BRepPrimAPI_MakeBox(gp_Pnt(*lo), gp_Pnt(*hi)).Shape()
    op = BRepAlgoAPI_Common(shape, box)
    op.Build()
    if not op.IsDone():
        raise ValueError("section cut failed")
    return op.Shape()


def _edge_points(edge) -> list[vec.Vec3]:
    curve = BRepAdaptor_Curve(edge)
    u0, u1 = curve.FirstParameter(), curve.LastParameter()
    t = curve.GetType()
    if t == GeomAbs_CurveType.GeomAbs_Line:
        n = 1
    elif t == GeomAbs_CurveType.GeomAbs_Circle:
        n = max(2, math.ceil(abs(u1 - u0) / (2 * math.pi) * CIRCLE_SEGMENTS))
    else:
        n = 48
    pts = []
    for k in range(n + 1):
        p = curve.Value(u0 + (u1 - u0) * k / n)
        pts.append((p.X(), p.Y(), p.Z()))
    if edge.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
        pts.reverse()
    return pts


def _cut_face_loops(cut: TopoDS_Shape, i: int, plane: float, view: ViewDef, frame) -> list[list[tuple[float, float]]]:
    """Closed loops (view-local mm) of every face lying in the cutting plane."""
    xmin, _, _, ymax = frame
    tol = 1e-4 * (1 + abs(plane))
    loops: list[list[tuple[float, float]]] = []
    for sub in iter_shapes(cut, TopAbs_ShapeEnum.TopAbs_FACE):
        face = TopoDS.Face_s(sub)
        surf = BRepAdaptor_Surface(face, True)
        if surf.GetType() != GeomAbs_SurfaceType.GeomAbs_Plane:
            continue
        pl = surf.Plane()
        d = pl.Axis().Direction()
        if abs(abs((d.X(), d.Y(), d.Z())[i]) - 1) > 1e-6:
            continue
        loc = pl.Location()
        if abs((loc.X(), loc.Y(), loc.Z())[i] - plane) > tol:
            continue
        for w in iter_shapes(face, TopAbs_ShapeEnum.TopAbs_WIRE):
            exp = BRepTools_WireExplorer(TopoDS.Wire_s(w), face)
            pts3: list[vec.Vec3] = []
            while exp.More():
                e = exp.Current()
                if not BRep_Tool.Degenerated_s(e):
                    seg = _edge_points(e)
                    pts3.extend(seg if not pts3 else seg[1:])
                exp.Next()
            if len(pts3) < 3:
                continue
            loop = []
            for p in pts3:
                x, y = view.project(p)
                loop.append((round(x - xmin, 4) + 0.0, round(ymax - y, 4) + 0.0))
            loops.append(loop)
    return loops


def section_view(
    shape: TopoDS_Shape,
    geometry: PartGeometry,
    view: ViewDef,
    base: ViewProjection,
    depth: float,
    part_diag: float,
) -> SectionProjection:
    i, s = cut_axis(view)
    depth = min(max(depth, 0.0), geometry.size[i])
    plane = plane_at(geometry, view, depth)
    cut = _cut(shape, geometry, i, s, plane)

    # Features that survive the cut keep their centre marks / axis lines.
    eps = 1e-6
    kept: list[CylinderFeature] = []
    for f in geometry.features:
        lo = min(f.start[i], f.end[i]) - (f.radius if abs(f.axis[i]) < 1e-6 else 0)
        hi = max(f.start[i], f.end[i]) + (f.radius if abs(f.axis[i]) < 1e-6 else 0)
        if (s > 0 and lo < plane - eps) or (s < 0 and hi > plane + eps):
            kept.append(f)

    proj = project_view(cut, view, kept, part_diag, frame=base.bbox)
    # A section shows what is cut and what lies behind it; hidden lines are omitted.
    proj.hidden = proj.hidden.model_copy(update={"primitives": [], "svg_path": ""})
    proj.tangent_hidden = proj.tangent_hidden.model_copy(update={"primitives": [], "svg_path": ""})
    return SectionProjection(
        view=view.name, depth=round(depth, 4), plane=round(plane, 4), axis=i, sign=s,
        projection=proj, regions=_cut_face_loops(cut, i, plane, view, base.bbox),
    )

"""OpenCascade Hidden-Line-Removal projection -> exact 2D primitives + SVG paths.

We drive ``HLRBRep_Algo`` directly (same engine build123d's
``Shape.project_to_viewport`` uses) so we can keep sharp, silhouette and smooth
(tangent) edges in separate layers for the "Show Tangent Edges" toggle.

Lines and circular arcs are kept *exact* (line / arc / circle primitives).
Anything else (ellipses in the isometric view, splines) is discretised with a
chordal deviation well below plotter resolution.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepLib import BRepLib
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.GeomAbs import GeomAbs_CurveType
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.TopoDS import TopoDS, TopoDS_Shape

from . import vec
from .models import (
    ArcPrim,
    Centerline,
    CenterMark,
    CirclePrim,
    CylinderFeature,
    EdgeLayer,
    LinePrim,
    PolylinePrim,
    ViewProjection,
)
from .topo import iter_shapes
from .views import ViewDef

ND = 4  # output rounding (0.1 µm)
LAYERS = ("visible", "hidden", "tangent", "tangent_hidden")


# ---------------------------------------------------------------------------
# Internal primitive in projected y-up coordinates
# ---------------------------------------------------------------------------
@dataclass
class _Prim:
    kind: str
    data: dict
    bbox_pts: list[tuple[float, float]]


def _xy(p) -> tuple[float, float]:
    return (p.X(), p.Y())


def _sample(curve: BRepAdaptor_Curve, u0: float, u1: float, deflection: float):
    try:
        disc = GCPnts_QuasiUniformDeflection(curve, deflection, u0, u1)
        if disc.IsDone() and disc.NbPoints() >= 2:
            return [_xy(disc.Value(i)) for i in range(1, disc.NbPoints() + 1)]
    except Exception:
        pass
    n = 64
    return [_xy(curve.Value(u0 + (u1 - u0) * i / (n - 1))) for i in range(n)]


def _arc_bbox_pts(c, r, a0, span, ccw):
    """Endpoints + any axis-extreme points the arc passes through (exact bbox)."""
    pts = []
    for k in range(4):
        ang = k * math.pi / 2
        delta = (ang - a0) % (2 * math.pi) if ccw else (a0 - ang) % (2 * math.pi)
        if delta <= span + 1e-12:
            pts.append((c[0] + r * math.cos(ang), c[1] + r * math.sin(ang)))
    return pts


def _edge_to_prim(edge, deflection: float) -> _Prim | None:
    try:
        BRepLib.BuildCurves3d_s(edge, 1e-6)
    except Exception:
        pass
    curve = BRepAdaptor_Curve(edge)
    u0, u1 = curve.FirstParameter(), curve.LastParameter()
    if not (math.isfinite(u0) and math.isfinite(u1)) or u1 - u0 <= 1e-12:
        return None
    ctype = curve.GetType()

    if ctype == GeomAbs_CurveType.GeomAbs_Line:
        p0, p1 = _xy(curve.Value(u0)), _xy(curve.Value(u1))
        if math.dist(p0, p1) < 1e-7:
            return None
        return _Prim("line", {"p0": p0, "p1": p1}, [p0, p1])

    if ctype == GeomAbs_CurveType.GeomAbs_Circle:
        circ = curve.Circle()
        axz = circ.Axis().Direction().Z()
        if abs(abs(axz) - 1.0) < 1e-6:  # circle lies in the projection plane
            c = _xy(circ.Location())
            r = circ.Radius()
            span = u1 - u0
            if span >= 2 * math.pi - 1e-6:
                return _Prim(
                    "circle",
                    {"c": c, "r": r},
                    [(c[0] - r, c[1] - r), (c[0] + r, c[1] + r)],
                )
            p0, p1 = _xy(curve.Value(u0)), _xy(curve.Value(u1))
            ccw = axz > 0  # parameter increases CCW in y-up space
            a0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
            pts = [p0, p1] + _arc_bbox_pts(c, r, a0, span, ccw)
            # Flipping y (to SVG space) turns CCW into the SVG positive sweep.
            data = {"c": c, "r": r, "p0": p0, "p1": p1,
                    "large": int(span > math.pi), "sweep": int(ccw)}
            return _Prim("arc", data, pts)

    pts = _sample(curve, u0, u1, deflection)
    if len(pts) < 2:
        return None
    return _Prim("polyline", {"pts": pts}, pts)


# ---------------------------------------------------------------------------
# HLR
# ---------------------------------------------------------------------------
def _run_hlr(shape: TopoDS_Shape, view: ViewDef) -> dict[str, list]:
    algo = HLRBRep_Algo()
    algo.Add(shape)
    frame = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*view.normal), gp_Dir(*view.x_dir))
    algo.Projector(HLRAlgo_Projector(frame))
    algo.Update()
    algo.Hide()

    hlr = HLRBRep_HLRToShape(algo)
    compounds = {
        "visible": [hlr.VCompound(), hlr.OutLineVCompound()],
        "hidden": [hlr.HCompound(), hlr.OutLineHCompound()],
        "tangent": [hlr.Rg1LineVCompound()],
        "tangent_hidden": [hlr.Rg1LineHCompound()],
    }
    out: dict[str, list] = {}
    for layer, comps in compounds.items():
        edges = []
        for comp in comps:
            if comp is None:
                continue
            edges.extend(TopoDS.Edge_s(e) for e in iter_shapes(comp, TopAbs_ShapeEnum.TopAbs_EDGE))
        out[layer] = edges
    return out


# ---------------------------------------------------------------------------
# Output conversion (projected y-up  ->  view-local SVG y-down)
# ---------------------------------------------------------------------------
def _n(v: float) -> str:
    s = f"{v:.{ND}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "", "-") else s


def primitives_to_svg_path(prims) -> str:
    parts: list[str] = []
    for p in prims:
        if p.type == "line":
            parts.append(f"M{_n(p.p0[0])} {_n(p.p0[1])}L{_n(p.p1[0])} {_n(p.p1[1])}")
        elif p.type == "arc":
            parts.append(
                f"M{_n(p.p0[0])} {_n(p.p0[1])}"
                f"A{_n(p.r)} {_n(p.r)} 0 {p.large} {p.sweep} {_n(p.p1[0])} {_n(p.p1[1])}"
            )
        elif p.type == "circle":
            cx, cy, r = p.c[0], p.c[1], p.r
            parts.append(
                f"M{_n(cx + r)} {_n(cy)}"
                f"A{_n(r)} {_n(r)} 0 1 0 {_n(cx - r)} {_n(cy)}"
                f"A{_n(r)} {_n(r)} 0 1 0 {_n(cx + r)} {_n(cy)}Z"
            )
        elif p.type == "polyline":
            pts = p.pts
            parts.append(
                f"M{_n(pts[0][0])} {_n(pts[0][1])}"
                + "".join(f"L{_n(x)} {_n(y)}" for x, y in pts[1:])
            )
    return "".join(parts)


class _Local:
    def __init__(self, xmin: float, ymax: float):
        self.xmin, self.ymax = xmin, ymax

    def pt(self, p) -> tuple[float, float]:
        return (round(p[0] - self.xmin, ND) + 0.0, round(self.ymax - p[1], ND) + 0.0)


def _to_model(prim: _Prim, t: _Local):
    d = prim.data
    if prim.kind == "line":
        return LinePrim(p0=t.pt(d["p0"]), p1=t.pt(d["p1"]))
    if prim.kind == "arc":
        return ArcPrim(c=t.pt(d["c"]), r=round(d["r"], ND), p0=t.pt(d["p0"]),
                       p1=t.pt(d["p1"]), large=d["large"], sweep=d["sweep"])
    if prim.kind == "circle":
        return CirclePrim(c=t.pt(d["c"]), r=round(d["r"], ND))
    return PolylinePrim(pts=[t.pt(p) for p in d["pts"]])


# ---------------------------------------------------------------------------
# Feature annotations per view (center marks & centerlines)
# ---------------------------------------------------------------------------
def _project_features(features: list[CylinderFeature], view: ViewDef, t: _Local):
    if view.is_isometric:
        return [], []

    marks: dict[tuple, CenterMark] = {}
    lines: dict[tuple, list[list]] = {}
    for f in features:
        if f.kind not in ("hole", "boss"):
            continue
        along = vec.dot(f.axis, view.normal)
        if abs(along) > 0.999:  # axis points at the viewer -> circle -> center mark
            cx, cy = t.pt(view.project(f.center))
            key = (round(cx, 3), round(cy, 3))
            m = marks.get(key)
            if m is None:
                marks[key] = CenterMark(cx=cx, cy=cy, r=f.radius, feature_ids=[f.id])
            else:
                m.r = max(m.r, f.radius)
                m.feature_ids.append(f.id)
        elif abs(along) < 1e-3:  # axis in the view plane -> centerline
            a, b = t.pt(view.project(f.start)), t.pt(view.project(f.end))
            dx, dy = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(dx, dy)
            if ln < 1e-9:
                continue
            u = (dx / ln, dy / ln)
            if u[0] < -1e-9 or (abs(u[0]) <= 1e-9 and u[1] < 0):
                u = (-u[0], -u[1])
            off = u[0] * a[1] - u[1] * a[0]
            ta, tb = sorted((u[0] * a[0] + u[1] * a[1], u[0] * b[0] + u[1] * b[1]))
            key = (round(math.atan2(u[1], u[0]), 4), round(off, 3))
            lines.setdefault(key, []).append([ta, tb, [f.id], u, off])

    centerlines: list[Centerline] = []
    gap_tol = 1.0  # merge coaxial segments that touch / overlap (e.g. shaft steps)
    for segs in lines.values():
        segs.sort(key=lambda s: s[0])
        merged = [segs[0]]
        for s in segs[1:]:
            cur = merged[-1]
            if s[0] <= cur[1] + gap_tol:
                cur[1] = max(cur[1], s[1])
                cur[2] = cur[2] + s[2]
            else:
                merged.append(s)
        for ta, tb, ids, u, off in merged:
            nrm = (-u[1], u[0])
            p0 = (ta * u[0] + off * nrm[0], ta * u[1] + off * nrm[1])
            p1 = (tb * u[0] + off * nrm[0], tb * u[1] + off * nrm[1])
            centerlines.append(Centerline(
                p0=(round(p0[0], ND) + 0.0, round(p0[1], ND) + 0.0),
                p1=(round(p1[0], ND) + 0.0, round(p1[1], ND) + 0.0),
                feature_ids=ids,
            ))
    return list(marks.values()), centerlines


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def project_view(
    shape: TopoDS_Shape,
    view: ViewDef,
    features: list[CylinderFeature],
    part_diag: float,
) -> ViewProjection:
    t0 = time.perf_counter()
    deflection = min(0.05, max(0.002, part_diag * 2e-4))

    raw = _run_hlr(shape, view)
    prims: dict[str, list[_Prim]] = {}
    for layer in LAYERS:
        prims[layer] = [p for e in raw[layer] if (p := _edge_to_prim(e, deflection)) is not None]

    all_pts = [pt for layer in LAYERS for p in prims[layer] for pt in p.bbox_pts]
    if all_pts:
        xs, ys = [p[0] for p in all_pts], [p[1] for p in all_pts]
        xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    else:
        xmin = xmax = ymin = ymax = 0.0

    t = _Local(xmin, ymax)
    layers: dict[str, EdgeLayer] = {}
    for layer in LAYERS:
        models = [_to_model(p, t) for p in prims[layer]]
        layers[layer] = EdgeLayer(primitives=models, svg_path=primitives_to_svg_path(models))

    marks, clines = _project_features(features, view, t)
    r = lambda v: round(v, ND) + 0.0  # noqa: E731
    return ViewProjection(
        name=view.name,
        is_isometric=view.is_isometric,
        view_dir=vec.clean3(view.normal),
        x_dir=vec.clean3(view.x_dir),
        y_dir=vec.clean3(view.y_dir),
        bbox=(r(xmin), r(ymin), r(xmax), r(ymax)),
        width=r(xmax - xmin),
        height=r(ymax - ymin),
        center_marks=marks,
        centerlines=clines,
        compute_ms=round((time.perf_counter() - t0) * 1000, 1),
        **layers,
    )

"""Higher-level feature recognition on top of the raw B-Rep faces.

* Chamfers: short conical faces bounded by two circles, coaxial with a
  cylinder (edge breaks on shafts and hole mouths). Drill-point cones (one
  boundary collapses to the apex) and long tapers are ignored.
* Slots / keyways: two concave half-cylinders of equal radius, parallel axes,
  same depth range, facing each other -> one obround slot.
"""
from __future__ import annotations

import math

from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp_Face
from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_SurfaceType
from OCP.gp import gp_Pnt, gp_Vec
from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.TopoDS import TopoDS, TopoDS_Shape

from . import vec
from .models import ChamferFeature, CylinderFeature, SlotFeature
from .topo import iter_shapes

CHAMFER_MAX_FRACTION = 0.35  # leg lengths must be small vs. the radius they break
CHAMFER_MAX_LEG = 10.0  # mm


def _p(p) -> vec.Vec3:
    return (p.X(), p.Y(), p.Z())


# ---------------------------------------------------------------------------
# Chamfers
# ---------------------------------------------------------------------------
def extract_chamfers(shape: TopoDS_Shape) -> list[ChamferFeature]:
    out: list[ChamferFeature] = []
    for sub in iter_shapes(shape, TopAbs_ShapeEnum.TopAbs_FACE):
        face = TopoDS.Face_s(sub)
        surf = BRepAdaptor_Surface(face, True)
        if surf.GetType() != GeomAbs_SurfaceType.GeomAbs_Cone:
            continue
        cone = surf.Cone()
        d = (cone.Axis().Direction().X(), cone.Axis().Direction().Y(), cone.Axis().Direction().Z())
        loc = _p(cone.Axis().Location())

        # boundary circles of the conical face: (radius, axial position)
        rings: dict[tuple, tuple[float, float]] = {}
        for e in iter_shapes(face, TopAbs_ShapeEnum.TopAbs_EDGE):
            curve = BRepAdaptor_Curve(TopoDS.Edge_s(e))
            if curve.GetType() != GeomAbs_CurveType.GeomAbs_Circle:
                continue
            circ = curve.Circle()
            t = vec.dot(vec.sub(_p(circ.Location()), loc), d)
            rings[(round(circ.Radius(), 5), round(t, 5))] = (circ.Radius(), t)
        if len(rings) != 2:
            continue  # drill-point cone (apex), partial cone, or something exotic
        (r1, t1), (r2, t2) = sorted(rings.values())
        if r1 < 1e-6:
            continue
        axial, radial = abs(t2 - t1), abs(r2 - r1)
        r_big = max(r1, r2)
        if axial < 1e-6 or radial < 1e-6:
            continue
        if max(axial, radial) > min(CHAMFER_MAX_LEG, CHAMFER_MAX_FRACTION * r_big):
            continue  # a taper, not an edge break

        # orientation-aware normal: points toward the axis => hole-mouth chamfer
        u0, u1 = surf.FirstUParameter(), surf.LastUParameter()
        v0, v1 = surf.FirstVParameter(), surf.LastVParameter()
        p, n = gp_Pnt(), gp_Vec()
        BRepGProp_Face(face).Normal((u0 + u1) / 2, (v0 + v1) / 2, p, n)
        rel = vec.sub(_p(p), loc)
        radial_dir = vec.sub(rel, vec.scale(d, vec.dot(rel, d)))
        internal = vec.dot((n.X(), n.Y(), n.Z()), radial_dir) < 0

        dc, sgn = vec.canonical_direction(d)
        p_small = vec.add(loc, vec.scale(d, t1))
        p_big = vec.add(loc, vec.scale(d, t2))
        out.append(ChamferFeature(
            id="",
            axis=vec.clean3(dc),
            axial=vec.clean(axial, 4),
            radial=vec.clean(radial, 4),
            angle_deg=vec.clean(math.degrees(math.atan2(radial, axial)), 3),
            r_small=vec.clean(r1, 4),
            r_big=vec.clean(r2, 4),
            p_small=vec.clean3(p_small, 4),
            p_big=vec.clean3(p_big, 4),
            internal=internal,
        ))
    out.sort(key=lambda c: (c.internal, vec.clean3(c.p_big, 3)))
    for i, c in enumerate(out, start=1):
        c.id = f"C{i}"
    return out


def chamfer_label(c: ChamferFeature) -> str:
    from .features import fmt_mm

    if abs(c.angle_deg - 45.0) < 0.5:
        return f"{fmt_mm(c.axial)}x45°"
    return f"{fmt_mm(c.axial)}x{round(c.angle_deg)}°"


# ---------------------------------------------------------------------------
# Slots / keyways
# ---------------------------------------------------------------------------
def find_slots(features: list[CylinderFeature], solids: list[TopoDS_Shape], eps: float) -> list[SlotFeature]:
    from .features import _end_open

    arcs = [f for f in features if f.kind == "concave_arc" and abs(f.angular_span_deg - 180.0) < 2.0]
    used: set[str] = set()
    slots: list[SlotFeature] = []
    for i, a in enumerate(arcs):
        if a.id in used:
            continue
        for b in arcs[i + 1:]:
            if b.id in used or abs(a.radius - b.radius) > 1e-4 or abs(vec.dot(a.axis, b.axis)) < 0.9999:
                continue
            # same depth range along the shared axis direction
            ta = sorted((vec.dot(a.start, a.axis), vec.dot(a.end, a.axis)))
            tb = sorted((vec.dot(b.start, a.axis), vec.dot(b.end, a.axis)))
            if abs(ta[0] - tb[0]) > 1e-3 or abs(ta[1] - tb[1]) > 1e-3:
                continue
            gap = vec.sub(b.center, a.center)
            gap = vec.sub(gap, vec.scale(a.axis, vec.dot(gap, a.axis)))
            dist = vec.norm(gap)
            if dist < 1e-3:
                continue
            direction = vec.scale(gap, 1 / dist)
            through = _end_open(solids, a.start, vec.scale(a.axis, -1), a.radius, eps) and _end_open(
                solids, a.end, a.axis, a.radius, eps
            )
            slots.append(SlotFeature(
                id=f"S{len(slots) + 1}",
                width=vec.clean(2 * a.radius, 4),
                length=vec.clean(dist + 2 * a.radius, 4),
                center_distance=vec.clean(dist, 4),
                depth=vec.clean(a.length, 4),
                axis=a.axis,
                direction=vec.clean3(direction, 6),
                c1=a.center,
                c2=b.center,
                through=through,
                feature_ids=[a.id, b.id],
            ))
            used.update((a.id, b.id))
            break
    return slots


def slot_label(s: SlotFeature) -> str:
    from .features import fmt_mm

    tail = "THRU" if s.through else f"DEPTH {fmt_mm(s.depth)}"
    return f"SLOT {fmt_mm(s.width)}x{fmt_mm(s.length)} {tail}"

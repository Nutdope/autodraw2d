"""Deterministic B-Rep inspection: bounding box, mass properties, cylinders.

Every number here comes straight from OpenCascade — this is the single source
of truth that the layout engine, AI annotator and exporters are fed.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from OCP.Bnd import Bnd_Box
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepGProp import BRepGProp, BRepGProp_Face
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Pnt, gp_Vec
from OCP.TopAbs import TopAbs_ShapeEnum, TopAbs_State
from OCP.TopoDS import TopoDS, TopoDS_Shape

from . import vec
from .models import CylinderFeature, FeatureGroup, PartGeometry
from .topo import iter_shapes

FULL_TURN = 2 * math.pi


# ---------------------------------------------------------------------------
# Global properties
# ---------------------------------------------------------------------------
def tight_bounding_box(shape: TopoDS_Shape) -> tuple[vec.Vec3, vec.Vec3]:
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return (xmin, ymin, zmin), (xmax, ymax, zmax)


def mass_properties(shape: TopoDS_Shape) -> tuple[float, float, vec.Vec3]:
    vprops = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, vprops)
    sprops = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, sprops)
    com = vprops.CentreOfMass()
    return vprops.Mass(), sprops.Mass(), (com.X(), com.Y(), com.Z())


# ---------------------------------------------------------------------------
# Cylindrical features
# ---------------------------------------------------------------------------
@dataclass
class _CylAcc:
    axis: vec.Vec3
    axis_point: vec.Vec3  # point on the axis line closest to the world origin
    radius: float
    internal: bool
    tmin: float = math.inf
    tmax: float = -math.inf
    span: float = 0.0
    faces: int = 0
    _keys: list = field(default_factory=list)


def _pnt(p) -> vec.Vec3:
    return (p.X(), p.Y(), p.Z())


def _collect_cylinders(shape: TopoDS_Shape) -> list[_CylAcc]:
    """Group cylindrical faces by (axis line, radius, internal) and merge extents.

    OCC frequently splits one logical hole into several faces (seams, cuts);
    grouping restores a single feature per physical cylinder.
    """
    groups: dict[tuple, _CylAcc] = {}
    for sub in iter_shapes(shape, TopAbs_ShapeEnum.TopAbs_FACE):
        face = TopoDS.Face_s(sub)
        surf = BRepAdaptor_Surface(face, True)
        if surf.GetType() != GeomAbs_SurfaceType.GeomAbs_Cylinder:
            continue

        cyl = surf.Cylinder()
        r = cyl.Radius()
        ax = cyl.Axis()
        loc = _pnt(ax.Location())
        d = (ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z())
        u0, u1 = surf.FirstUParameter(), surf.LastUParameter()
        v0, v1 = surf.FirstVParameter(), surf.LastVParameter()
        if not all(math.isfinite(x) for x in (u0, u1, v0, v1)):
            continue

        # Orientation-aware normal decides hole (normal points to axis) vs boss.
        p, n = gp_Pnt(), gp_Vec()
        BRepGProp_Face(face).Normal((u0 + u1) / 2, (v0 + v1) / 2, p, n)
        pt = _pnt(p)
        rel = vec.sub(pt, loc)
        radial = vec.sub(rel, vec.scale(d, vec.dot(rel, d)))
        internal = vec.dot((n.X(), n.Y(), n.Z()), radial) < 0

        dc, sgn = vec.canonical_direction(d)
        q = vec.sub(loc, vec.scale(dc, vec.dot(loc, dc)))
        key = (vec.clean3(dc, 5), vec.clean3(q, 3), vec.clean(r, 4), internal)
        acc = groups.get(key)
        if acc is None:
            acc = groups[key] = _CylAcc(axis=dc, axis_point=q, radius=r, internal=internal)

        base_t = vec.dot(loc, dc)
        ta, tb = base_t + sgn * v0, base_t + sgn * v1
        acc.tmin = min(acc.tmin, ta, tb)
        acc.tmax = max(acc.tmax, ta, tb)
        acc.span += abs(u1 - u0)
        acc.faces += 1
    return list(groups.values())


def _point_in_material(solids: list[TopoDS_Shape], p: vec.Vec3, tol: float) -> bool:
    gp = gp_Pnt(*p)
    for s in solids:
        state = BRepClass3d_SolidClassifier(s, gp, tol).State()
        if state in (TopAbs_State.TopAbs_IN, TopAbs_State.TopAbs_ON):
            return True
    return False


def _axis_label(d: vec.Vec3) -> str | None:
    for i, name in enumerate("XYZ"):
        if abs(abs(d[i]) - 1.0) < 1e-6:
            return name
    return None


def fmt_mm(v: float) -> str:
    """Engineering number format: at least one decimal, at most two."""
    s = f"{v:.2f}"
    if s.endswith("0"):
        s = s[:-1]
    return s


def extract_features(shape: TopoDS_Shape, part_size: float) -> list[CylinderFeature]:
    solids = list(iter_shapes(shape, TopAbs_ShapeEnum.TopAbs_SOLID))
    eps = max(0.01, 1e-4 * part_size)

    raw: list[tuple] = []
    for acc in _collect_cylinders(shape):
        full = acc.span >= FULL_TURN * 0.999
        if full:
            kind = "hole" if acc.internal else "boss"
        else:
            kind = "concave_arc" if acc.internal else "convex_arc"

        start = vec.add(acc.axis_point, vec.scale(acc.axis, acc.tmin))
        end = vec.add(acc.axis_point, vec.scale(acc.axis, acc.tmax))
        center = vec.scale(vec.add(start, end), 0.5)

        through = None
        if kind == "hole":
            # Probe just past each end on the axis. Beyond a THRU hole there is air
            # on both sides; beyond a blind hole's bottom there is material.
            # 0.65·r clears a standard 118° drill-point cone.
            probe = 0.65 * acc.radius + eps
            through = not (
                _point_in_material(solids, vec.sub(start, vec.scale(acc.axis, probe)), eps / 10)
                or _point_in_material(solids, vec.add(end, vec.scale(acc.axis, probe)), eps / 10)
            )

        raw.append((kind, acc, start, end, center, through, full))

    order = {"boss": 0, "hole": 1, "convex_arc": 2, "concave_arc": 3}
    raw.sort(key=lambda t: (order[t[0]], -t[1].radius, vec.clean3(t[4], 3)))

    features: list[CylinderFeature] = []
    for i, (kind, acc, start, end, center, through, full) in enumerate(raw, start=1):
        features.append(
            CylinderFeature(
                id=f"F{i}",
                kind=kind,
                radius=vec.clean(acc.radius, 4),
                diameter=vec.clean(2 * acc.radius, 4),
                axis=vec.clean3(acc.axis),
                axis_aligned=_axis_label(acc.axis),
                start=vec.clean3(start, 4),
                end=vec.clean3(end, 4),
                center=vec.clean3(center, 4),
                length=vec.clean(acc.tmax - acc.tmin, 4),
                angular_span_deg=vec.clean(360.0 if full else math.degrees(acc.span), 3),
                through=through,
                face_count=acc.faces,
            )
        )
    return features


def group_features(features: list[CylinderFeature]) -> list[FeatureGroup]:
    buckets: dict[tuple, list[CylinderFeature]] = defaultdict(list)
    for f in features:
        if f.kind == "hole":
            depth = None if f.through else round(f.length, 3)
            key = (f.kind, round(f.diameter, 3), vec.clean3(f.axis, 4), f.through, depth)
        elif f.kind == "boss":
            key = (f.kind, round(f.diameter, 3), vec.clean3(f.axis, 4))
        else:
            key = (f.kind, round(f.radius, 3), vec.clean3(f.axis, 4))
        buckets[key].append(f)

    groups: list[FeatureGroup] = []
    for members in buckets.values():
        f0 = members[0]
        n = len(members)
        prefix = f"{n}x " if n > 1 else ""
        if f0.kind == "hole":
            tail = " THRU" if f0.through else f" DEPTH {fmt_mm(f0.length)}"
            label = f"{prefix}Ø{fmt_mm(f0.diameter)}{tail}"
        elif f0.kind == "boss":
            label = f"{prefix}Ø{fmt_mm(f0.diameter)}"
        else:
            label = f"{prefix}R{fmt_mm(f0.radius)}"
        groups.append(
            FeatureGroup(
                kind=f0.kind,
                label=label,
                count=n,
                diameter=f0.diameter if f0.kind in ("hole", "boss") else None,
                radius=f0.radius,
                axis=f0.axis,
                through=f0.through,
                feature_ids=[m.id for m in members],
            )
        )
    return groups


def analyze_geometry(shape: TopoDS_Shape) -> PartGeometry:
    bmin, bmax = tight_bounding_box(shape)
    size = vec.sub(bmax, bmin)
    volume, area, com = mass_properties(shape)
    features = extract_features(shape, max(size))
    return PartGeometry(
        bbox_min=vec.clean3(bmin, 4),
        bbox_max=vec.clean3(bmax, 4),
        size=vec.clean3(size, 4),
        volume=vec.clean(volume, 3),
        surface_area=vec.clean(area, 3),
        center_of_mass=vec.clean3(com, 4),
        solid_count=sum(1 for _ in iter_shapes(shape, TopAbs_ShapeEnum.TopAbs_SOLID)),
        face_count=sum(1 for _ in iter_shapes(shape, TopAbs_ShapeEnum.TopAbs_FACE)),
        features=features,
        feature_groups=group_features(features),
    )

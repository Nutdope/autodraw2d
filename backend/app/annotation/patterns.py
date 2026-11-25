"""Hole patterns that a drawing states with one callout instead of coordinates.

Bolt circle: >= 3 identical holes with parallel axes whose centres lie on one
circle at equal angular pitch -> "6x Ø8.0 THRU EQ SP ON PCD Ø60.0". The
pitch-circle centre is the reference, so the holes need no x/y positions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..geometry import vec
from ..geometry.features import fmt_mm
from ..geometry.models import PartAnalysis

TOL = 1e-2


@dataclass(frozen=True)
class BoltCircle:
    group_label: str
    feature_ids: tuple[str, ...]
    axis: vec.Vec3
    center: vec.Vec3
    pcd: float
    centers: tuple[vec.Vec3, ...]

    @property
    def label(self) -> str:
        return f"{self.group_label} EQ SP ON PCD Ø{fmt_mm(self.pcd)}"


def _fit(centers: list[vec.Vec3], axis: vec.Vec3) -> tuple[vec.Vec3, float] | None:
    """Centre + radius if the points sit on one circle at equal pitch, else None."""
    n = len(centers)
    c = vec.scale((sum(p[0] for p in centers), sum(p[1] for p in centers), sum(p[2] for p in centers)), 1 / n)
    radii = []
    for p in centers:
        rel = vec.sub(p, c)
        if abs(vec.dot(rel, axis)) > TOL:  # not coplanar
            return None
        radii.append(vec.norm(rel))
    r = sum(radii) / n
    if r < 1e-3 or any(abs(x - r) > TOL for x in radii):
        return None
    # equal pitch: sorted angles step by 360/n
    u = vec.normalize(vec.sub(centers[0], c))
    w = vec.cross(axis, u)
    angs = sorted(math.atan2(vec.dot(vec.sub(p, c), w), vec.dot(vec.sub(p, c), u)) % (2 * math.pi) for p in centers)
    step = 2 * math.pi / n
    if any(abs((b - a) - step) > 1e-3 for a, b in zip(angs, angs[1:])):
        return None
    return c, r


def bolt_circles(a: PartAnalysis) -> list[BoltCircle]:
    g = a.geometry
    by_id = {f.id: f for f in g.features}
    out: list[BoltCircle] = []
    for grp in g.feature_groups:
        if grp.kind != "hole" or grp.count < 3:
            continue
        # counterbored groups also list the cbore ids: keep the drilled holes only
        holes = [by_id[i] for i in grp.feature_ids if i in by_id and abs(by_id[i].diameter - (grp.diameter or 0)) < 1e-6]
        if len(holes) < 3:
            continue
        centers = [h.center for h in holes]
        fit = _fit(centers, holes[0].axis)
        if fit is None:
            continue
        c, r = fit
        hub = any(
            f.kind in ("hole", "boss") and abs(abs(vec.dot(f.axis, holes[0].axis)) - 1) < 1e-6
            and vec.norm(vec.sub(vec.sub(f.center, c), vec.scale(f.axis, vec.dot(vec.sub(f.center, c), f.axis)))) < TOL
            for f in g.features
        )
        if len(holes) == 4 and not hub:
            continue  # a square of 4 holes on a plate reads better as a grid
        out.append(BoltCircle(grp.label, tuple(h.id for h in holes), holes[0].axis,
                              vec.clean3(c, 4), round(2 * r, 4), tuple(centers)))
    return out

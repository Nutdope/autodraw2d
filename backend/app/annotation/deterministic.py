"""Deterministic auto-dimensioner — always available, zero cost, never wrong.

Rules of thumb it follows (ISO 129-1 / ASME Y14.5 style):
* every feature is dimensioned once, in the view that shows its true shape
* hole groups get a single callout ("4x Ø8.0 THRU") + baseline positions from datum edges
* shafts: Ø across each step (on the part) + chain of step lengths
* fillets/rounds: radius callout where the arc is seen true
* overall L × W × H outermost, never duplicated
* dimension lines stack 7 / 13 / 19 mm from the view, inside the 25 mm clearance
"""
from __future__ import annotations

import math
from collections import defaultdict

from ..geometry import vec
from ..geometry.features import fmt_mm
from ..geometry.models import PartAnalysis
from .context import ViewCtx, build_contexts
from .models import CircleDim, DimensionMode, LinearDim

FIRST_LEVEL = 7.0
LEVEL_STEP = 6.0  # 7 / 13 / 19 mm: outermost text (+~4.5 mm) still clears the 25 mm view gap
MAX_LEVELS = 3
MAX_POSITION_DIMS = 4
OPPOSITE = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}
SIGN = {"top": 1.0, "bottom": -1.0, "right": 1.0, "left": -1.0}

VIEW_PRIORITY = ("front", "top", "right", "left", "bottom", "rear")


def base_notes(mode: DimensionMode, tolerance: str) -> list[str]:
    if mode == "none":
        return []
    notes = [f"GENERAL TOLERANCES: {tolerance.upper()}", "DIMENSIONS IN MILLIMETRES"]
    if mode in ("key", "full"):
        notes.append("BREAK ALL SHARP EDGES")
    return notes


class _Builder:
    def __init__(self, analysis: PartAnalysis, ctx: dict[str, ViewCtx]) -> None:
        self.a = analysis
        self.ctx = ctx
        self.order = [v for v in VIEW_PRIORITY if v in ctx]
        self.dims: list = []
        self._levels: dict[tuple[str, str], int] = defaultdict(int)
        self._n = 0
        self._chain_views: set[tuple[str, str]] = set()  # (view, orientation) used by shaft chains
        self._used_angles: dict[str, list[float]] = defaultdict(list)

    # -- helpers -----------------------------------------------------------
    def _id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}{self._n}"

    def _offset(self, view: str, side: str) -> float:
        """Next free stacking level on `side`, spilling to the opposite side when full."""
        for s in (side, OPPOSITE[side]):
            n = self._levels[(view, s)]
            if n < MAX_LEVELS:
                self._levels[(view, s)] += 1
                return SIGN[s] * (FIRST_LEVEL + LEVEL_STEP * n)
        n = self._levels[(view, side)]
        self._levels[(view, side)] += 1
        return SIGN[side] * (FIRST_LEVEL + LEVEL_STEP * n)

    def _linear(self, view, p1, p2, orientation, side=None, value=None, prefix="", from_points=False):
        x1, y1 = p1
        x2, y2 = p2
        if value is None:
            value = abs(x2 - x1) if orientation == "horizontal" else abs(y2 - y1)
        if value < 0.01:
            return None
        offset = 0.0 if from_points else self._offset(view, side)
        d = LinearDim(
            id=self._id("L"), view=view, x1=x1, y1=y1, x2=x2, y2=y2, orientation=orientation,
            offset_mm=offset, offset_from="points" if from_points else "edge",
            value_mm=round(value, 4), prefix=prefix,
        )
        self.dims.append(d)
        return d

    def _has_linear(self, view: str, orientation: str, value: float) -> bool:
        return any(
            isinstance(d, LinearDim) and d.view == view and d.orientation == orientation
            and abs(d.value_mm - value) < 1e-3
            for d in self.dims
        )

    def _leader(self, v: ViewCtx, cx: float, cy: float) -> tuple[float, float]:
        """(angle, length) for a callout: the most outward diagonal not yet used in
        this view, so neighbouring callouts fan out instead of stacking."""
        dx, dy = cx - v.w / 2, v.h / 2 - cy  # y-up
        ang = 45.0 if abs(dx) < 1e-6 and abs(dy) < 1e-6 else math.degrees(math.atan2(dy, dx)) % 360
        diag = sorted((45.0, 135.0, 315.0, 225.0), key=lambda c: min(abs(ang - c), 360 - abs(ang - c)))
        used = self._used_angles[v.name]
        for c in diag:
            if c not in used:
                used.append(c)
                return c, 10.0
        used.append(diag[0])
        return diag[0], 10.0 + 8.0 * (len(used) - 4)

    # -- feature rules -----------------------------------------------------
    def holes(self) -> None:
        groups = [g for g in self.a.geometry.feature_groups if g.kind == "hole"]
        hole_marks: dict[str, list] = defaultdict(list)
        for g in groups:
            ids = set(g.feature_ids)
            best, best_marks = None, []
            for name in self.order:
                marks = [m for m in self.ctx[name].vp.center_marks if ids & set(m.feature_ids)]
                if len(marks) > len(best_marks):
                    best, best_marks = name, marks
            if not best:
                continue
            v = self.ctx[best]
            # Put the callout on the hole furthest up-right so the leader points away from the part.
            m = max(best_marks, key=lambda mk: (mk.cx - mk.cy))
            r = next(f.radius for f in self.a.geometry.features if f.id in ids)
            angle, length = self._leader(v, m.cx, m.cy)
            self.dims.append(CircleDim(
                type="diameter", id=self._id("D"), view=best, cx=m.cx, cy=m.cy, radius=r,
                leader_angle_deg=angle, leader_len_mm=length,
                label_text=g.label, feature_ids=g.feature_ids,
            ))
            hole_marks[best].extend(best_marks)

        for name, marks in hole_marks.items():
            v = self.ctx[name]
            by_x: dict[float, object] = {}
            by_y: dict[float, object] = {}
            for mk in marks:
                by_x.setdefault(round(mk.cx, 3), mk)
                by_y.setdefault(round(mk.cy, 3), mk)
            for x in sorted(by_x)[:MAX_POSITION_DIMS]:  # baseline from the left edge
                if 1e-6 < x < v.w - 1e-6:
                    mk = by_x[x]
                    self._linear(name, (0.0, 0.0), (mk.cx, mk.cy), "horizontal", "top")
            for y in sorted(by_y, reverse=True)[:MAX_POSITION_DIMS]:  # baseline from the bottom edge
                if 1e-6 < y < v.h - 1e-6:
                    mk = by_y[y]
                    self._linear(name, (0.0, v.h), (mk.cx, mk.cy), "vertical", "left")

    def bosses(self) -> None:
        bosses = [f for f in self.a.geometry.features if f.kind == "boss"]
        if not bosses:
            return
        name = next(
            (n for n in self.order if all(abs(vec.dot(f.axis, self.ctx[n].vd.normal)) < 1e-3 for f in bosses)),
            None,
        )
        if name is None:
            return
        v = self.ctx[name]
        segs = []
        for f in bosses:
            a, b = v.local(f.start), v.local(f.end)
            horizontal_axis = abs(a[1] - b[1]) < 1e-6
            segs.append((f, a, b, horizontal_axis))

        for f, a, b, hax in segs:
            if hax:
                xm, cy = (a[0] + b[0]) / 2, a[1]
                self._linear(name, (xm, cy - f.radius), (xm, cy + f.radius), "vertical",
                             value=f.diameter, prefix="Ø", from_points=True)
            else:
                ym, cx = (a[1] + b[1]) / 2, a[0]
                self._linear(name, (cx - f.radius, ym), (cx + f.radius, ym), "horizontal",
                             value=f.diameter, prefix="Ø", from_points=True)

        # chain of step lengths along each coaxial axis
        for hax in (True, False):
            group = [s for s in segs if s[3] == hax]
            if not group:
                continue
            k = 0 if hax else 1
            bounds = sorted({round(c, 4) for _, a, b, _ in group for c in (a[k], b[k])})
            if len(bounds) <= 2:
                continue
            # End chamfers/rounds shorten the outer cylinders; step lengths are
            # measured to the end faces, so snap near-edge bounds onto the part ends.
            extent = v.w if hax else v.h
            if 0 < bounds[0] <= 0.05 * extent:
                bounds[0] = 0.0
            if extent - 0.05 * extent <= bounds[-1] < extent:
                bounds[-1] = round(extent, 4)

            def surface(t: float) -> tuple[float, float]:
                def gap(s) -> float:
                    lo, hi = sorted((s[1][k], s[2][k]))
                    return max(lo - t, t - hi, 0.0)

                nearest = min(gap(s) for s in group)
                covering = [s for s in group if gap(s) <= nearest + 1e-6]
                f, a, _, _ = max(covering, key=lambda s: s[0].radius)
                return (t, a[1] - f.radius) if hax else (a[0] - f.radius, t)

            orientation = "horizontal" if hax else "vertical"
            side = "top" if hax else "left"
            off = self._offset(name, side)
            for t0, t1 in zip(bounds, bounds[1:]):
                d = LinearDim(
                    id=self._id("L"), view=name, x1=surface(t0)[0], y1=surface(t0)[1],
                    x2=surface(t1)[0], y2=surface(t1)[1], orientation=orientation,
                    offset_mm=off, offset_from="edge", value_mm=round(t1 - t0, 4),
                )
                self.dims.append(d)
            self._chain_views.add((name, orientation))

    def arcs(self) -> None:
        for g in self.a.geometry.feature_groups:
            if g.kind not in ("concave_arc", "convex_arc"):
                continue
            ids = set(g.feature_ids)
            for name in self.order:
                arc = next((am for am in self.ctx[name].vp.arc_marks if am.feature_id in ids), None)
                if arc is None:
                    continue
                self.dims.append(CircleDim(
                    type="radius", id=self._id("R"), view=name, cx=arc.cx, cy=arc.cy, radius=arc.r,
                    leader_angle_deg=arc.mid_angle_deg, leader_len_mm=12.0 if arc.concave else 8.0,
                    inside=arc.concave, label_text=g.label, feature_ids=g.feature_ids,
                ))
                break

    def profile_steps(self) -> None:
        """Full mode: chain dimensions for plate thicknesses / steps read off the profile."""
        for name in self.order[:2]:
            v = self.ctx[name]
            lines = [p for p in v.vp.visible.primitives if p.type == "line"]
            vert = [p for p in lines if abs(p.p0[0] - p.p1[0]) < 1e-6]
            horiz = [p for p in lines if abs(p.p0[1] - p.p1[1]) < 1e-6]

            xs = sorted({round(p.p0[0], 3) for p in vert})
            if 3 <= len(xs) <= 6 and (name, "horizontal") not in self._chain_views:
                off = self._offset(name, "bottom")
                lowest = {x: max(max(p.p0[1], p.p1[1]) for p in vert if round(p.p0[0], 3) == x) for x in xs}
                for x0, x1 in zip(xs, xs[1:]):
                    self.dims.append(LinearDim(
                        id=self._id("L"), view=name, x1=x0, y1=lowest[x0], x2=x1, y2=lowest[x1],
                        orientation="horizontal", offset_mm=off, offset_from="edge", value_mm=round(x1 - x0, 4),
                    ))

            ys = sorted({round(p.p0[1], 3) for p in horiz})
            if 3 <= len(ys) <= 6 and (name, "vertical") not in self._chain_views:
                off = self._offset(name, "right")
                rightmost = {y: max(max(p.p0[0], p.p1[0]) for p in horiz if round(p.p0[1], 3) == y) for y in ys}
                for y0, y1 in zip(ys, ys[1:]):
                    self.dims.append(LinearDim(
                        id=self._id("L"), view=name, x1=rightmost[y0], y1=y0, x2=rightmost[y1], y2=y1,
                        orientation="vertical", offset_mm=off, offset_from="edge", value_mm=round(y1 - y0, 4),
                    ))

    def overall(self) -> None:
        assigned: dict[str, tuple[str, str]] = {}
        for name in self.order:
            v = self.ctx[name]
            for which, orient in (("x", "horizontal"), ("y", "vertical")):
                ax = v.axis_of(which)
                if ax and ax not in assigned:
                    assigned[ax] = (name, orient)
        for name, orient in assigned.values():
            v = self.ctx[name]
            size = v.w if orient == "horizontal" else v.h
            if self._has_linear(name, orient, size):
                continue  # e.g. shaft Ø30 already states the height
            if orient == "horizontal":
                self._linear(name, (0.0, 0.0), (v.w, 0.0), "horizontal", "top")
            else:
                self._linear(name, (0.0, v.h), (0.0, 0.0), "vertical", "left")


def deterministic_dimensions(analysis: PartAnalysis, views: list[str], mode: DimensionMode) -> list:
    if mode == "none":
        return []
    b = _Builder(analysis, build_contexts(analysis, views))
    if mode in ("key", "full"):
        b.holes()
        b.bosses()
        b.arcs()
    if mode == "full":
        b.profile_steps()
    b.overall()
    return b.dims


def describe(d) -> str:
    """Short human/LLM-readable summary of a dimension (used in the AI payload)."""
    if isinstance(d, LinearDim):
        return f"{d.view}: {d.orientation} {d.prefix}{fmt_mm(d.value_mm)} ({d.x1},{d.y1})->({d.x2},{d.y2})"
    return f"{d.view}: {d.type} {d.label_text} at ({d.cx},{d.cy})"

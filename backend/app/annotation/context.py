"""Per-view geometric context shared by the deterministic dimensioner, the AI
payload builder and the AI validator.

``anchors`` is the closed set of points a dimension may attach to. The AI is
shown these points and every coordinate it returns is snapped back onto one of
them — anything that doesn't snap is discarded.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..geometry import VIEW_DEFS, ViewDef, vec
from ..geometry.models import PartAnalysis, ViewProjection

MAX_ANCHORS = 140


@dataclass
class Anchor:
    x: float
    y: float
    kind: str  # corner | center | quadrant | arc_center | arc_mid | axis_end | vertex


@dataclass
class ViewCtx:
    name: str
    vp: ViewProjection
    vd: ViewDef
    anchors: list[Anchor] = field(default_factory=list)

    @property
    def w(self) -> float:
        return self.vp.width

    @property
    def h(self) -> float:
        return self.vp.height

    def local(self, p: vec.Vec3) -> tuple[float, float]:
        x, y = self.vd.project(p)
        return (round(x - self.vp.bbox[0], 4), round(self.vp.bbox[3] - y, 4))

    def axis_of(self, which: str) -> str | None:
        """World axis ('X'/'Y'/'Z') running along the view's local x or y, if aligned."""
        d = self.vd.x_dir if which == "x" else self.vd.y_dir
        for i, name in enumerate("XYZ"):
            if abs(abs(d[i]) - 1) < 1e-6:
                return name
        return None

    def signed_axis(self, which: str) -> str:
        d = self.vd.x_dir if which == "x" else self.vd.y_dir
        if which == "y":  # local y points DOWN on paper
            d = vec.scale(d, -1)
        for i, name in enumerate("XYZ"):
            if abs(abs(d[i]) - 1) < 1e-6:
                return ("+" if d[i] > 0 else "-") + name
        return "oblique"


def _build_anchors(v: ViewCtx) -> list[Anchor]:
    seen: set[tuple[float, float]] = set()
    out: list[Anchor] = []

    def add(x: float, y: float, kind: str) -> None:
        key = (round(x, 3), round(y, 3))
        if key in seen or len(out) >= MAX_ANCHORS:
            return
        seen.add(key)
        out.append(Anchor(key[0] + 0.0, key[1] + 0.0, kind))

    w, h = v.w, v.h
    for x, y in ((0, 0), (w, 0), (0, h), (w, h)):
        add(x, y, "corner")
    for m in v.vp.center_marks:
        add(m.cx, m.cy, "center")
        for dx, dy in ((m.r, 0), (-m.r, 0), (0, m.r), (0, -m.r)):
            add(m.cx + dx, m.cy + dy, "quadrant")
    for a in v.vp.arc_marks:
        add(a.cx, a.cy, "arc_center")
        for dx, dy in ((a.r, 0), (-a.r, 0), (0, a.r), (0, -a.r)):
            add(a.cx + dx, a.cy + dy, "arc_quadrant")  # e.g. the far ends of a slot
    for c in v.vp.centerlines:
        add(*c.p0, "axis_end")
        add(*c.p1, "axis_end")
    for layer in (v.vp.visible, v.vp.hidden):
        for p in layer.primitives:
            if p.type in ("line", "arc"):
                add(*p.p0, "vertex")
                add(*p.p1, "vertex")
    return out


def build_contexts(analysis: PartAnalysis, views: list[str]) -> dict[str, ViewCtx]:
    out: dict[str, ViewCtx] = {}
    for name in views:
        if name not in analysis.views or name == "isometric":
            continue
        ctx = ViewCtx(name, analysis.views[name], VIEW_DEFS[name])
        ctx.anchors = _build_anchors(ctx)
        out[name] = ctx
    return out

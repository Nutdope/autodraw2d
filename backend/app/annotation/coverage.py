"""Dimension completeness: is every edge position on the drawing tied to a datum?

A drawing is fully dimensioned along a world axis when every "interesting"
coordinate along it (face positions seen edge-on, hole / boss centres) can be
reached from the part's datum by a chain of dimensions. We model that with a
union-find per world axis:

* nodes  = coordinates (world mm, rounded), collected from the active ortho
  views: straight edges seen edge-on, centre marks and axis lines.
* edges  = every linear dimension (its two end points along its axis), plus
  the relations a feature callout already fixes: a Ø callout fixes centre ± r,
  a hole's DEPTH / THRU fixes both its ends, a slot callout fixes its sides
  and ends, a radius fixes the fillet's tangent lines.

Whatever is not connected to the datum (the smallest coordinate) is missing.
``fill_gaps`` then adds chain dimensions for exactly those coordinates, in the
view where they are seen best, so no edge is left floating.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ..geometry import vec
from ..geometry.models import PartAnalysis
from .context import ViewCtx, build_contexts
from .models import LinearDim

ND = 2  # coordinates are compared at 0.01 mm
MIN_EDGE = 0.05  # ignore sliver edges (tessellation / seam noise)
MAX_CHAIN = 8  # never add more than this many gap dims along one view axis
VIEW_PRIORITY = ("front", "top", "right", "left", "bottom", "rear")
AXES = "XYZ"


def _key(v: float) -> float:
    return round(v, ND) + 0.0


class _UF:
    def __init__(self) -> None:
        self.parent: dict[float, float] = {}

    def find(self, a: float) -> float:
        a = _key(a)
        self.parent.setdefault(a, a)
        root = a
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[a] != root:  # path compression
            self.parent[a], a = root, self.parent[a]
        return root

    def union(self, a: float, b: float) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


# ---------------------------------------------------------------------------
# view-local <-> world coordinate along one world axis
# ---------------------------------------------------------------------------
def _axis_index(d: vec.Vec3) -> tuple[int, float] | None:
    for i in range(3):
        if abs(abs(d[i]) - 1) < 1e-6:
            return i, (1.0 if d[i] > 0 else -1.0)
    return None


def world_of(v: ViewCtx, which: str, local: float) -> tuple[int, float] | None:
    """(axis index, world coordinate) of a local x / y value, if the axis is aligned."""
    if which == "x":
        ai = _axis_index(v.vd.x_dir)
        if ai is None:
            return None
        return ai[0], ai[1] * (local + v.vp.bbox[0])
    ai = _axis_index(v.vd.y_dir)
    if ai is None:
        return None
    return ai[0], ai[1] * (v.vp.bbox[3] - local)


def local_of(v: ViewCtx, which: str, world: float) -> float:
    if which == "x":
        _, s = _axis_index(v.vd.x_dir)  # type: ignore[misc]
        return world * s - v.vp.bbox[0]
    _, s = _axis_index(v.vd.y_dir)  # type: ignore[misc]
    return v.vp.bbox[3] - world * s


# ---------------------------------------------------------------------------
# Where each coordinate can be seen (for picking dimension end points)
# ---------------------------------------------------------------------------
@dataclass
class Sighting:
    view: str
    which: str  # "x" | "y" : the local axis the coordinate runs along
    local: float
    point: tuple[float, float]  # a point on the geometry at that coordinate
    visible: bool
    kind: str  # edge | center


def _straight(p) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """End points of a line, or of a polyline that is really an axis-aligned line
    (circles seen edge-on come out of HLR as sampled curves)."""
    if p.type == "line":
        return p.p0, p.p1
    if p.type != "polyline" or len(p.pts) < 2:
        return None
    xs, ys = [q[0] for q in p.pts], [q[1] for q in p.pts]
    if max(xs) - min(xs) < 1e-4:
        return (xs[0], min(ys)), (xs[0], max(ys))
    if max(ys) - min(ys) < 1e-4:
        return (min(xs), ys[0]), (max(xs), ys[0])
    return None


def _sightings(ctx: dict[str, ViewCtx]) -> dict[int, dict[float, list[Sighting]]]:
    out: dict[int, dict[float, list[Sighting]]] = {i: defaultdict(list) for i in range(3)}

    def add(v: ViewCtx, which: str, local: float, pt, visible: bool, kind: str) -> None:
        w = world_of(v, which, local)
        if w is not None:
            out[w[0]][_key(w[1])].append(Sighting(v.name, which, local, pt, visible, kind))

    for v in ctx.values():
        for layer, visible in ((v.vp.visible, True), (v.vp.hidden, False)):
            for p in layer.primitives:
                seg = _straight(p)
                if seg is None:
                    continue
                (x0, y0), (x1, y1) = seg
                if abs(x0 - x1) < 1e-6 and abs(y1 - y0) >= MIN_EDGE:  # vertical: an x position
                    add(v, "x", x0, (x0, min(y0, y1)), visible, "edge")
                    add(v, "x", x0, (x0, max(y0, y1)), visible, "edge")
                elif abs(y0 - y1) < 1e-6 and abs(x1 - x0) >= MIN_EDGE:  # horizontal: a y position
                    add(v, "y", y0, (min(x0, x1), y0), visible, "edge")
                    add(v, "y", y0, (max(x0, x1), y0), visible, "edge")
        for m in v.vp.center_marks:
            add(v, "x", m.cx, (m.cx, m.cy), True, "center")
            add(v, "y", m.cy, (m.cx, m.cy), True, "center")
        for c in v.vp.centerlines:
            (x0, y0), (x1, y1) = c.p0, c.p1
            if abs(x0 - x1) < 1e-6:
                add(v, "x", x0, (x0, min(y0, y1)), True, "center")
            elif abs(y0 - y1) < 1e-6:
                add(v, "y", y0, (min(x0, x1), y0), True, "center")
    return out


# ---------------------------------------------------------------------------
# Relations fixed by feature callouts
# ---------------------------------------------------------------------------
def _feature_relations(a: PartAnalysis, ufs: list[_UF]) -> None:
    g = a.geometry
    for f in g.features:
        for i in range(3):
            if abs(f.axis[i]) > 0.999:  # along the axis
                if f.kind == "hole":  # Ø.. THRU / DEPTH .. fixes both ends from the mouth
                    ufs[i].union(f.start[i], f.end[i])
                continue
            if abs(f.axis[i]) > 1e-6:
                continue  # oblique axis: no aligned relation
            c = f.center[i]
            ufs[i].union(c - f.radius, c)  # Ø / R callout fixes centre ± r
            ufs[i].union(c + f.radius, c)
    for sl in g.slots:
        for i in range(3):
            c1, c2 = sl.c1[i], sl.c2[i]
            r = sl.width / 2
            for p in (c1 - r, c1 + r, c2 - r, c2 + r, c2):
                ufs[i].union(c1, p)
            if abs(sl.axis[i]) > 0.999 and sl.depth:
                ufs[i].union(c1 - sl.axis[i] * sl.depth / 2, c1 + sl.axis[i] * sl.depth / 2)
        # A slot wall cutting a shaft leaves an edge at c ± sqrt(r² - d²): fixed by the
        # slot width and the shaft Ø, so it is derived, not a size to dimension.
        side = vec.cross(sl.axis, sl.direction)
        j = next((n for n in range(3) if abs(side[n]) > 0.999), None)
        if j is None:
            continue
        for f in g.features:
            if f.kind != "boss":
                continue
            ia = next((n for n in range(3) if abs(f.axis[n]) > 0.999), None)
            if ia is None or ia == j:
                continue
            k = 3 - ia - j
            for p in (sl.c1[j] - sl.width / 2, sl.c1[j] + sl.width / 2):
                d = p - f.center[j]
                if abs(d) < f.radius:
                    h = (f.radius ** 2 - d * d) ** 0.5
                    ufs[k].union(f.center[k] + h, f.center[k])
                    ufs[k].union(f.center[k] - h, f.center[k])
    for ch in g.chamfers:  # "1.0x45°" fixes both legs
        for i in range(3):
            ufs[i].union(ch.p_small[i], ch.p_big[i])
            if abs(ch.axis[i]) < 1e-6:
                for p, r in ((ch.p_small, ch.r_small), (ch.p_big, ch.r_big)):
                    ufs[i].union(p[i] - r, p[i])
                    ufs[i].union(p[i] + r, p[i])
    # bolt circles: "EQ SP ON PCD" fixes every hole centre from the circle's centre
    from .patterns import bolt_circles

    for bc in bolt_circles(a):
        for i in range(3):
            if abs(bc.axis[i]) > 0.999:
                continue
            for c in bc.centers:
                ufs[i].union(c[i], bc.center[i])


def _dimension_relations(dims: list, ctx: dict[str, ViewCtx], ufs: list[_UF]) -> None:
    for d in dims:
        if not isinstance(d, LinearDim) or d.view not in ctx:
            continue
        v = ctx[d.view]
        which = "x" if d.orientation == "horizontal" else "y"
        a = world_of(v, which, d.x1 if which == "x" else d.y1)
        b = world_of(v, which, d.x2 if which == "x" else d.y2)
        if a and b:
            ufs[a[0]].union(a[1], b[1])


@dataclass
class Gap:
    axis: str
    world: float
    sightings: list[Sighting]
    group: float  # union-find root: gaps sharing it are already tied to each other


def find_gaps(a: PartAnalysis, views: list[str], dims: list) -> list[Gap]:
    ctx = build_contexts(a, views)
    seen = _sightings(ctx)
    ufs = [_UF() for _ in range(3)]
    _feature_relations(a, ufs)
    _dimension_relations(dims, ctx, ufs)
    gaps: list[Gap] = []
    for i in range(3):
        coords = sorted(seen[i])
        if not coords:
            continue
        # The datum is the part's extreme face (min); the overall size links the max.
        datum = ufs[i].find(_key(a.geometry.bbox_min[i]))
        for c in coords:
            if ufs[i].find(c) != datum:
                gaps.append(Gap(AXES[i], c, seen[i][c], ufs[i].find(c)))
    return gaps


# ---------------------------------------------------------------------------
# Filling the gaps
# ---------------------------------------------------------------------------
def fill_gaps(a: PartAnalysis, views: list[str], dims: list, offset_for, new_id) -> list[LinearDim]:
    """Chain-dimension every coordinate that isn't tied to the datum yet.

    ``offset_for(view, side)`` hands out stacking levels, ``new_id(prefix)`` ids,
    so the added dims stack with the ones already placed.
    """
    ctx = build_contexts(a, views)
    added: list[LinearDim] = []
    order = [v for v in VIEW_PRIORITY if v in ctx]
    for _ in range(3):  # a new dim can make other coordinates reachable: iterate
        gaps = find_gaps(a, views, dims + added)
        if not gaps:
            break
        # One link per group of coordinates that are already tied together (a hole's
        # centre and both its edges): dimension its best representative only —
        # a centre mark over an edge, visible over hidden, then by view priority.
        rank = lambda s: (s.kind != "center", not s.visible, order.index(s.view))  # noqa: E731
        reps: dict[tuple[str, float], tuple[float, Sighting]] = {}
        for g in gaps:
            best = min(g.sightings, key=rank)
            cur = reps.get((g.axis, g.group))
            if cur is None or rank(best) < rank(cur[1]):
                reps[(g.axis, g.group)] = (g.world, best)
        plan: dict[tuple[str, str], list[tuple[float, Sighting]]] = defaultdict(list)
        for world, best in reps.values():
            plan[(best.view, best.which)].append((world, best))
        progress = False
        for (view, which), items in plan.items():
            v = ctx[view]
            ai = _axis_index(v.vd.x_dir if which == "x" else v.vd.y_dir)
            if ai is None:
                continue
            seen = _sightings({view: v})[ai[0]]
            chain = _chain(a, v, which, items[:MAX_CHAIN], seen, dims + added)
            if not chain:
                continue
            # top / left like every other rule: bottom / right face the neighbouring
            # views in both ISO and ANSI arrangements and would share their gap
            side = "top" if which == "x" else "left"
            k = 0 if which == "x" else 1
            span = (min(min(p[k], q[k]) for p, q, _ in chain), max(max(p[k], q[k]) for p, q, _ in chain))
            off = offset_for(view, side, span)
            for p, q, value in chain:
                added.append(LinearDim(
                    id=new_id("G"), view=view, x1=p[0], y1=p[1], x2=q[0], y2=q[1],
                    orientation="horizontal" if which == "x" else "vertical",
                    offset_mm=off, offset_from="edge", value_mm=round(value, 4),
                ))
            progress = True
        if not progress:
            break
    return added


def _chain(a: PartAnalysis, v: ViewCtx, which: str, items, seen, dims) -> list:
    """Chain from the nearest connected coordinate through every gap on this axis."""
    ufs = [_UF() for _ in range(3)]
    _feature_relations(a, ufs)
    _dimension_relations(dims, {v.name: v}, ufs)
    # dims in other views also connect coordinates (same world axis)
    ctx_all = build_contexts(a, list(a.views))
    _dimension_relations(dims, ctx_all, ufs)
    ai = _axis_index(v.vd.x_dir if which == "x" else v.vd.y_dir)
    i = ai[0]  # type: ignore[index]
    datum = ufs[i].find(_key(a.geometry.bbox_min[i]))
    anchors = [c for c in seen if ufs[i].find(c) == datum]
    if not anchors:
        return []
    gaps = sorted(w for w, _ in items)
    # start from the connected coordinate closest to the first gap
    start = min(anchors, key=lambda c: abs(c - gaps[0]))
    pts = sorted({start, *gaps})
    # the chain must run monotonic in local space; sort by local coordinate
    locs = sorted(pts, key=lambda w: local_of(v, which, w))

    def point(w: float) -> tuple[float, float]:
        cands = seen.get(_key(w), [])
        if not cands:
            loc = local_of(v, which, w)
            return (loc, 0.0) if which == "x" else (0.0, loc)
        # extension lines start from the side the dimension sits on (top / left)
        if which == "x":
            s = max(cands, key=lambda s: (s.visible, -s.point[1]))
        else:
            s = max(cands, key=lambda s: (s.visible, -s.point[0]))
        return s.point

    out = []
    for w0, w1 in zip(locs, locs[1:]):
        p, q = point(w0), point(w1)
        val = abs(w1 - w0)
        if val < 0.01:
            continue
        out.append((p, q, val))
    return out


def stacker(a: PartAnalysis, dims: list):
    """(offset_for, new_id) for adding dims to a finished set (AI / cached layouts):
    the first stacking level not yet used on that side of the view."""
    from .deterministic import Levels

    levels = Levels(lambda v: (a.views[v].width, a.views[v].height))
    for d in dims:
        if isinstance(d, LinearDim) and d.offset_from == "edge" and d.view in a.views:
            if d.orientation == "horizontal":
                side, span = ("top" if d.offset_mm >= 0 else "bottom"), (min(d.x1, d.x2), max(d.x1, d.x2))
            else:
                side, span = ("right" if d.offset_mm >= 0 else "left"), (min(d.y1, d.y2), max(d.y1, d.y2))
            levels.reserve(d.view, side, d.offset_mm, span)
    counter = [0]
    offset_for = levels.offset

    def new_id(prefix: str) -> str:
        counter[0] += 1
        return f"{prefix}x{counter[0]}"

    return offset_for, new_id


def complete(a: PartAnalysis, views: list[str], dims: list) -> list:
    """Add whatever an externally produced set (AI, cache) leaves undimensioned."""
    offset_for, new_id = stacker(a, dims)
    return dims + fill_gaps(a, views, dims, offset_for, new_id)

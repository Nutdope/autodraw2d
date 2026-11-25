"""Paper-space decorations of a full section (ISO 128-44 / ISO 128-50).

* hatching: thin 45° lines, 2.5 mm apart on paper, clipped (even-odd) to the
  faces lying in the cutting plane. Phase is tied to the paper, so separate
  regions of one part hatch in step.
* cutting-plane line in a view that shows the plane edge-on: thin chain line,
  thick at both ends, arrows in the direction of sight and the letter.
* "SECTION A-A" under the sectioned view.

Computed once here, so the screen and every export format draw the same thing.
"""
from __future__ import annotations

import math
from typing import Mapping, Optional

from ..geometry import VIEW_DEFS
from ..geometry.models import SectionProjection, ViewProjection
from .models import OverlayLine, OverlayText, SectionOverlay, SheetLayout, ViewPlacement

HATCH_SPACING = 2.5  # paper mm, measured perpendicular to the lines
THICK_IN = 3.0  # thick end: this far into the view outline...
THICK_OUT = 6.0  # ...and this far beyond it
ARROW_LEN = 7.0
ARROW_HEAD = (3.0, 1.0)  # length, half width
LETTER_SIZE = 5.0
LABEL_SIZE = 5.0
LABEL_GAP = 8.0
LETTER = "A"
PARENT_PRIORITY = ("front", "top", "bottom", "right", "left", "rear")


def hatch_lines(loops: list[list[tuple[float, float]]], spacing: float = HATCH_SPACING):
    """45° hatch (rising to the right on paper, y down) clipped even-odd to `loops`."""
    edges = []
    for loop in loops:
        n = len(loop)
        for k in range(n):
            p, q = loop[k], loop[(k + 1) % n]
            if p != q:
                edges.append((p, q))
    if not edges:
        return []
    fs = [x + y for loop in loops for x, y in loop]
    step = spacing * math.sqrt(2)  # along x + y, for `spacing` perpendicular
    out = []
    c = math.floor(min(fs) / step) * step + step / 2  # phase tied to the paper
    while c < max(fs):
        ts = []
        for (x0, y0), (x1, y1) in edges:
            f0, f1 = x0 + y0, x1 + y1
            if (f0 <= c < f1) or (f1 <= c < f0):
                t = (c - f0) / (f1 - f0)
                x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                ts.append(x - y)
        ts.sort()
        for a, b in zip(ts[0::2], ts[1::2]):
            if b - a > 1e-6:
                out.append(((c + a) / 2, (c - a) / 2, (c + b) / 2, (c - b) / 2))
        c += step
    return [tuple(round(v, 3) for v in seg) for seg in out]


def _parent(lay: SheetLayout, sec: SectionProjection) -> Optional[ViewPlacement]:
    """An active ortho view that shows the cutting plane edge-on."""
    by_view = {p.view: p for p in lay.placements if p.grid_cell is not None}
    for name in PARENT_PRIORITY:
        p = by_view.get(name)
        if p is None or name == sec.view:
            continue
        if abs(VIEW_DEFS[name].normal[sec.axis]) < 1e-9:
            return p
    return None


def _arrow(tip: tuple[float, float], d: tuple[float, float]) -> list[tuple[float, float]]:
    L, W = ARROW_HEAD
    bx, by = tip[0] - d[0] * L, tip[1] - d[1] * L
    return [tip, (bx - d[1] * W, by + d[0] * W), (bx + d[1] * W, by - d[0] * W)]


def build_overlay(
    sec: SectionProjection,
    lay: SheetLayout,
    views: Mapping[str, ViewProjection],
    auto: bool,
    depth_max: float,
) -> Optional[SectionOverlay]:
    place = next((p for p in lay.placements if p.view == sec.view), None)
    if place is None:
        return None
    s = place.scale
    P = lambda q: (place.x_offset + q[0] * s, place.y_offset + q[1] * s)  # noqa: E731
    hatch = hatch_lines([[P(q) for q in loop] for loop in sec.regions])

    lines: list[OverlayLine] = []
    arrows: list[list[tuple[float, float]]] = []
    texts: list[OverlayText] = []
    parent = _parent(lay, sec)
    if parent is not None:
        vd, vp = VIEW_DEFS[parent.view], views[parent.view]
        ps, r = parent.scale, parent.rect
        sight = -sec.sign  # direction of sight along the cut axis (viewer looks toward -n)
        if abs(vd.x_dir[sec.axis]) > 0.5:  # plane shows as a vertical line
            x = parent.x_offset + (vd.x_dir[sec.axis] * sec.plane - vp.bbox[0]) * ps
            ends = [((x, r.y), -1.0), ((x, r.y + r.h), 1.0)]
            d = (math.copysign(1.0, sight * vd.x_dir[sec.axis]), 0.0)
            vertical = True
        else:  # horizontal line
            y = parent.y_offset + (vp.bbox[3] - vd.y_dir[sec.axis] * sec.plane) * ps
            ends = [((r.x, y), -1.0), ((r.x + r.w, y), 1.0)]
            d = (0.0, -math.copysign(1.0, sight * vd.y_dir[sec.axis]))  # paper y is down
            vertical = False

        def along(pt, k):  # move along the cutting line
            return (pt[0], pt[1] + k) if vertical else (pt[0] + k, pt[1])

        (a, _), (b, _) = ends
        lines.append(OverlayLine(x1=along(a, THICK_IN)[0], y1=along(a, THICK_IN)[1],
                                 x2=along(b, -THICK_IN)[0], y2=along(b, -THICK_IN)[1], style="chain"))
        for pt, sgn in ends:
            outer, inner = along(pt, sgn * THICK_OUT), along(pt, -sgn * THICK_IN)
            lines.append(OverlayLine(x1=outer[0], y1=outer[1], x2=inner[0], y2=inner[1], style="thick"))
            base = along(pt, sgn * (THICK_OUT - 1.5))
            tip = (base[0] + d[0] * ARROW_LEN, base[1] + d[1] * ARROW_LEN)
            lines.append(OverlayLine(x1=base[0], y1=base[1], x2=tip[0], y2=tip[1], style="thin"))
            arrows.append([(round(x, 3), round(y, 3)) for x, y in _arrow(tip, d)])
            lx, ly = tip[0] + d[0] * 3.5, tip[1] + d[1] * 3.5
            texts.append(OverlayText(x=round(lx, 3), y=round(ly + LETTER_SIZE * 0.36, 3), text=LETTER,
                                     size=LETTER_SIZE))

    rect = place.rect
    label = OverlayText(x=round(rect.x + rect.w / 2, 3), y=round(rect.y + rect.h + LABEL_GAP, 3),
                        text=f"SECTION {LETTER}-{LETTER}", size=LABEL_SIZE)
    pr = sec.projection
    return SectionOverlay(
        view=sec.view, letter=LETTER, depth=sec.depth, depth_max=round(depth_max, 4), auto=auto,
        visible_svg=pr.visible.svg_path, tangent_svg=pr.tangent.svg_path,
        center_marks=pr.center_marks, centerlines=pr.centerlines,
        hatch=hatch, lines=lines, arrows=arrows, texts=texts, label=label,
    )


def label_y(label_y0: float, view_bottom: float, dims: list, view: str) -> float:
    """Drop the label below any dimensions placed under the section view."""
    lowest = 0.0
    for d in dims:
        if getattr(d, "view", None) != view or getattr(d, "type", None) != "linear":
            continue
        if d.orientation == "horizontal" and d.offset_from == "edge" and d.offset_mm < 0:
            lowest = max(lowest, -d.offset_mm)
    return max(label_y0, view_bottom + lowest + LABEL_GAP) if lowest else label_y0

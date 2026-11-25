"""Build the paper-space SheetModel from analysis + layout + the user's final state.

Geometry mirrors the frontend renderer (Sheet.tsx / TitleBlock.tsx /
Dimensions.tsx) so the exported sheet matches what the user saw.
"""
from __future__ import annotations

import math

from ..annotation.models import CircleDim, LinearDim
from ..geometry.models import PartAnalysis, ViewProjection
from ..layout.models import SheetLayout, ViewPlacement
from .models import Arc, Circle, ExportRequest, Line, Poly, SheetModel, Solid, Text

# ISO 129 / 3098 proportions (paper mm) — keep in sync with Dimensions.tsx
TEXT = 3.5
ARROW_L = 3.0
ARROW_W = 0.5
EXT_GAP = 1.0
EXT_OVER = 2.0
TEXT_LIFT = 1.2
CENTER_OVERSHOOT = 3.0


def text_width(s: str, size: float = TEXT) -> float:
    return len(s) * size * 0.56


def fit_size(text: str, width: float, size: float) -> float:
    est = len(text) * size * 0.56
    return max(1.6, width / est * size) if est > width else size


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------
def _view(m: SheetModel, v: ViewProjection, p: ViewPlacement, req: ExportRequest) -> None:
    s, xo, yo = p.scale, p.x_offset, p.y_offset

    def P(pt) -> tuple[float, float]:
        return (xo + pt[0] * s, yo + pt[1] * s)

    def emit(layer: str, prims) -> None:
        for q in prims:
            if q.type == "line":
                (x1, y1), (x2, y2) = P(q.p0), P(q.p1)
                m.add(Line(layer, x1, y1, x2, y2))
            elif q.type == "arc":
                c = P(q.c)
                m.add(Arc(layer, c[0], c[1], q.r * s, P(q.p0), P(q.p1), q.large, q.sweep))
            elif q.type == "circle":
                c = P(q.c)
                m.add(Circle(layer, c[0], c[1], q.r * s))
            else:
                m.add(Poly(layer, [P(pt) for pt in q.pts]))

    d = req.display
    if d.tangent:
        emit("TANGENT", v.tangent.primitives)
    if d.hidden:
        emit("HIDDEN", v.hidden.primitives)
        if d.tangent:
            emit("HIDDEN", v.tangent_hidden.primitives)
    emit("VISIBLE", v.visible.primitives)

    if d.centerlines and not v.is_isometric:
        for c in v.centerlines:
            (x0, y0), (x1, y1) = P(c.p0), P(c.p1)
            ln = math.hypot(x1 - x0, y1 - y0) or 1.0
            ux, uy = (x1 - x0) / ln, (y1 - y0) / ln
            m.add(Line("CENTERLINES", x0 - ux * CENTER_OVERSHOOT, y0 - uy * CENTER_OVERSHOOT,
                       x1 + ux * CENTER_OVERSHOOT, y1 + uy * CENTER_OVERSHOOT))
        for mk in v.center_marks:
            cx, cy = P((mk.cx, mk.cy))
            arm = mk.r * s + CENTER_OVERSHOOT
            m.add(Line("CENTERLINES", cx - arm, cy, cx + arm, cy), Line("CENTERLINES", cx, cy - arm, cx, cy + arm))


# ---------------------------------------------------------------------------
# Frame, zones, notes
# ---------------------------------------------------------------------------
def _frame(m: SheetModel, lay: SheetLayout) -> None:
    fr, z = lay.frame, lay.zones
    W, H = lay.page_width, lay.page_height
    right, bottom = fr.x + fr.w, fr.y + fr.h
    m.add(Poly("BORDER", [(fr.x, fr.y), (right, fr.y), (right, bottom), (fr.x, bottom)], closed=True, weight=m.thick))
    for x in z.col_edges[1:-1]:
        m.add(Line("BORDER", x, fr.y, x, fr.y - 5), Line("BORDER", x, bottom, x, bottom + 5))
    for y in z.row_edges[1:-1]:
        m.add(Line("BORDER", fr.x, y, fr.x - 5, y), Line("BORDER", right, y, right + 5, y))
    # centring marks
    m.add(
        Line("BORDER", W / 2, 0, W / 2, fr.y, weight=m.thick),
        Line("BORDER", W / 2, bottom, W / 2, H, weight=m.thick),
        Line("BORDER", 0, H / 2, fr.x, H / 2, weight=m.thick),
        Line("BORDER", right, H / 2, W, H / 2, weight=m.thick),
    )
    for i, c in enumerate(z.columns):
        cx = (z.col_edges[i] + z.col_edges[i + 1]) / 2
        m.add(Text("BORDER", cx, fr.y - 2.6, c, 3, "middle"), Text("BORDER", cx, bottom + 6.4, c, 3, "middle"))
    for i, r in enumerate(z.rows):
        cy = (z.row_edges[i] + z.row_edges[i + 1]) / 2 + 1.1
        m.add(Text("BORDER", fr.x - 10, cy, r, 3, "middle"), Text("BORDER", right + 5, cy, r, 3, "middle"))


def _notes(m: SheetModel, lay: SheetLayout, notes: list[str]) -> None:
    if not notes:
        return
    tb = lay.title_block
    top = tb.y - 4 - len(notes) * 4.5
    m.add(Text("DIMENSIONS", tb.x, top, "NOTES", 3.5, bold=True))
    for i, n in enumerate(notes):
        m.add(Text("DIMENSIONS", tb.x, top + (i + 1) * 4.5, f"{i + 1}. {n}", 3))


# ---------------------------------------------------------------------------
# Title block (mirror of TitleBlock.tsx)
# ---------------------------------------------------------------------------
def _projection_symbol(m: SheetModel, ox: float, oy: float, k: float, method: str) -> None:
    h, small, cone, gap = 10.0, 5.0, 10.0, 4.0
    cy = h / 2
    cone_x = 0.0 if method == "first_angle" else h + gap
    circ_x = cone + gap + h / 2 if method == "first_angle" else h / 2

    def T(x: float, y: float) -> tuple[float, float]:
        return (ox + x * k, oy + y * k)

    pts = [T(cone_x, cy - small / 2), T(cone_x + cone, cy - h / 2), T(cone_x + cone, cy + h / 2), T(cone_x, cy + small / 2)]
    c = T(circ_x, cy)
    m.add(
        Poly("TITLE_BLOCK", pts, closed=True),
        Circle("TITLE_BLOCK", c[0], c[1], h / 2 * k),
        Circle("TITLE_BLOCK", c[0], c[1], small / 2 * k),
        Line("CENTERLINES", *T(-1, cy), *T(cone + gap + h + 1, cy)),
        Line("CENTERLINES", *T(circ_x, -1), *T(circ_x, h + 1)),
    )


def _title_block(m: SheetModel, lay: SheetLayout, req: ExportRequest) -> None:
    tb = lay.title_block
    x, y, w, h = tb.x, tb.y, tb.w, tb.h
    r = h / 4
    L = min(108.0, w * 0.6)
    X = lambda v: x + v  # noqa: E731
    Y = lambda row: y + row * r  # noqa: E731
    f = req.title
    TB = "TITLE_BLOCK"

    m.add(Poly(TB, [(x, y), (x + w, y), (x + w, y + h), (x, y + h)], closed=True, weight=m.thick))
    for x1, y1, x2, y2 in [
        (X(0), Y(1), X(L), Y(1)), (X(0), Y(2), X(w), Y(2)), (X(0), Y(3), X(w), Y(3)),
        (X(L), Y(0), X(L), Y(4)), (X(L / 2), Y(0), X(L / 2), Y(1)),
        (X(L * 0.667), Y(1), X(L * 0.667), Y(3)), (X(L * 0.37), Y(3), X(L * 0.37), Y(4)),
        (X(L * 0.685), Y(3), X(L * 0.685), Y(4)), (X(w - 20), Y(2), X(w - 20), Y(4)),
    ]:
        m.add(Line(TB, x1, y1, x2, y2))

    def cell(cx: float, cy: float, cw: float, label: str, value: str, size: float = 3.2) -> None:
        v = value or "—"
        m.add(Text(TB, cx + 1.2, cy + 2.6, label, 1.8, muted=True),
              Text(TB, cx + 1.5, cy + r - 2.2, v, fit_size(v, cw - 3, size)))

    cell(X(0), Y(0), L / 2, "DRAWN BY", f.drawnBy)
    cell(X(L / 2), Y(0), L / 2, "DATE", f.date)
    cell(X(0), Y(1), L * 0.667, "MATERIAL", f.material)
    cell(X(L * 0.667), Y(1), L * 0.333, "SURFACE", f.roughness)
    cell(X(0), Y(2), L * 0.667, "GENERAL TOLERANCES", req.tolerance)
    cell(X(L * 0.667), Y(2), L * 0.333, "UNITS", "mm")
    proj = "PROJECTION (ISO E)" if lay.projection_method == "first_angle" else "PROJECTION (ISO A)"
    m.add(Text(TB, X(1.2), Y(3) + 2.6, proj, 1.8, muted=True))
    _projection_symbol(m, X(L * 0.185 - 26 * 0.35), Y(3) + 3.6, 0.7, lay.projection_method)
    cell(X(L * 0.37), Y(3), L * 0.315, "SCALE", lay.scale_label, 4)
    cell(X(L * 0.685), Y(3), L * 0.315, "SHEET", f"{lay.page_format} · 1/1")

    m.add(Text(TB, X(L + 1.2), Y(0) + 2.6, "TITLE", 1.8, muted=True))
    title = (f.partName or "UNTITLED").upper()
    m.add(Text(TB, X(L + (w - L) / 2), Y(1) + 2, title, fit_size(title, w - L - 4, 5.5), "middle", bold=True))
    cell(X(L), Y(2), w - L - 20, "DRAWING NO.", f.drawingNumber)
    cell(X(w - 20), Y(2), 20, "REV", f.revision, 4)
    m.add(Text(TB, X(L + 1.5), Y(4) - 2.4, "AutoDraw 2D", 3, bold=True),
          Text(TB, X(w - 18.5), Y(4) - 2.4, lay.standard, 2, muted=True))


# ---------------------------------------------------------------------------
# Dimensions (mirror of Dimensions.tsx)
# ---------------------------------------------------------------------------
def _arrow(m: SheetModel, tip: tuple[float, float], d: tuple[float, float]) -> None:
    bx, by = tip[0] - d[0] * ARROW_L, tip[1] - d[1] * ARROW_L
    nx, ny = -d[1] * ARROW_W, d[0] * ARROW_W
    m.add(Solid("DIMENSIONS", [tip, (bx + nx, by + ny), (bx - nx, by - ny)]))


def _linear(m: SheetModel, d: LinearDim, p: ViewPlacement, w: float, h: float) -> None:
    s = p.scale
    P1 = (p.x_offset + d.x1 * s, p.y_offset + d.y1 * s)
    P2 = (p.x_offset + d.x2 * s, p.y_offset + d.y2 * s)
    horiz = d.orientation == "horizontal"
    positive = d.offset_mm >= 0
    if horiz:
        ref = (p.y_offset if positive else p.y_offset + h * s) if d.offset_from == "edge" else \
            (min(P1[1], P2[1]) if positive else max(P1[1], P2[1]))
        line = ref - d.offset_mm
    else:
        ref = (p.x_offset + w * s if positive else p.x_offset) if d.offset_from == "edge" else \
            (max(P1[0], P2[0]) if positive else min(P1[0], P2[0]))
        line = ref + d.offset_mm

    along = (lambda q: q[0]) if horiz else (lambda q: q[1])
    across = (lambda q: q[1]) if horiz else (lambda q: q[0])
    mk = (lambda a, b: (a, b)) if horiz else (lambda a, b: (b, a))
    a1, a2 = sorted((along(P1), along(P2)))
    outside = a2 - a1 < 2 * ARROW_L + 2
    mid = (a1 + a2) / 2 + d.text_shift_mm

    for P in (P1, P2):
        b = across(P)
        if abs(b - line) < 0.5:
            continue
        sgn = 1.0 if line > b else -1.0
        m.add(Line("DIMENSIONS", *mk(along(P), b + sgn * EXT_GAP), *mk(along(P), line + sgn * EXT_OVER)))
    ext = ARROW_L + 2 if outside else 0.0
    m.add(Line("DIMENSIONS", *mk(a1 - ext, line), *mk(a2 + ext, line)))
    unit = (lambda k: (k, 0.0)) if horiz else (lambda k: (0.0, k))
    _arrow(m, mk(a1, line), unit(1.0 if outside else -1.0))
    _arrow(m, mk(a2, line), unit(-1.0 if outside else 1.0))

    label = f"{d.prefix}{fmt_value(d.value_mm)}" + (f" {d.tolerance_text}" if d.tolerance_text else "")
    tx, ty = (mid, line - TEXT_LIFT) if horiz else (line - TEXT_LIFT, mid)
    m.add(Text("DIMENSIONS", tx, ty, label, TEXT, "middle", rotation=0.0 if horiz else 90.0))


def _circle(m: SheetModel, d: CircleDim, p: ViewPlacement) -> None:
    s = p.scale
    C = (p.x_offset + d.cx * s, p.y_offset + d.cy * s)
    R = d.radius * s
    th = math.radians(d.leader_angle_deg)
    u = (math.cos(th), -math.sin(th))
    E = (C[0] + u[0] * R, C[1] + u[1] * R)
    sg = -1.0 if d.inside else 1.0
    K = (E[0] + sg * u[0] * d.leader_len_mm, E[1] + sg * u[1] * d.leader_len_mm)
    sx = 1.0 if K[0] - E[0] >= 0 else -1.0
    tw = text_width(d.label_text)
    m.add(Line("DIMENSIONS", *E, *K), Line("DIMENSIONS", *K, K[0] + sx * (tw + 2), K[1]))
    _arrow(m, E, (-sg * u[0], -sg * u[1]))
    m.add(Text("DIMENSIONS", K[0] + sx * (tw / 2 + 1), K[1] - TEXT_LIFT, d.label_text, TEXT, "middle"))


def fmt_value(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s or "0"


# ---------------------------------------------------------------------------
def build_sheet(analysis: PartAnalysis, lay: SheetLayout, req: ExportRequest) -> SheetModel:
    thick = 0.7 if lay.page_format in ("A1", "A2") else 0.5
    m = SheetModel(lay.page_width, lay.page_height, thick, thick / 2)
    _frame(m, lay)
    placements = {p.view: p for p in lay.placements}
    for p in lay.placements:
        _view(m, analysis.views[p.view], p, req)
        if p.scale != lay.scale:
            m.add(Text("DIMENSIONS", p.rect.x + p.rect.w / 2, p.rect.y + p.rect.h + 7,
                       f"{p.view.upper()} ({p.scale_label})", 3.5, "middle"))
    for d in req.dimensions:
        p = placements.get(d.view)
        v = analysis.views.get(d.view)
        if p is None or v is None:
            continue  # dimension belongs to a view that isn't on this sheet
        if isinstance(d, LinearDim):
            _linear(m, d, p, v.width, v.height)
        else:
            _circle(m, d, p)
    _notes(m, lay, req.notes)
    _title_block(m, lay, req)
    return m


__all__ = ["build_sheet"]

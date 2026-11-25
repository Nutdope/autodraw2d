"""Minimal server-side sheet renderer (used for CLI verification now and as the
base of the SVG/PDF exporter in Milestone 4).

Line weights follow ISO 128: thick (visible) / thin (hidden, center, dims).
Stroke widths and dash patterns are specified in *paper* mm, so they are
divided by the view scale inside each scaled <g>.
"""
from __future__ import annotations

import math
from typing import Mapping
from xml.sax.saxutils import escape

from ..geometry.models import ViewProjection
from ..layout.models import SheetLayout

CENTER_OVERSHOOT = 3.0  # mm on paper beyond the feature


def _f(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _dash(pattern: tuple[float, ...], s: float) -> str:
    return " ".join(_f(p / s) for p in pattern)


def render_sheet_svg(
    layout: SheetLayout,
    views: Mapping[str, ViewProjection],
    *,
    show_hidden: bool = True,
    show_centerlines: bool = True,
    show_tangent: bool = False,
    title: str = "",
) -> str:
    W, H = layout.page_width, layout.page_height
    thick = 0.7 if layout.page_format in ("A1", "A2") else 0.5
    thin = thick / 2
    hidden_dash = (3.0, 1.5)
    center_dash = (12.0, 2.0, 1.5, 2.0)
    o: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_f(W)}mm" height="{_f(H)}mm" '
        f'viewBox="0 0 {_f(W)} {_f(H)}" font-family="Arial, Helvetica, sans-serif">',
        f'<rect width="{_f(W)}" height="{_f(H)}" fill="#fff"/>',
    ]

    # --- frame + zones ------------------------------------------------------
    fr = layout.frame
    o.append(f'<rect x="{_f(fr.x)}" y="{_f(fr.y)}" width="{_f(fr.w)}" height="{_f(fr.h)}" '
             f'fill="none" stroke="#000" stroke-width="{thick}"/>')
    z = layout.zones
    g = ['<g stroke="#000" stroke-width="0.25" fill="#000" font-size="3.5" text-anchor="middle">']
    for x in z.col_edges[1:-1]:
        g.append(f'<line x1="{_f(x)}" y1="{_f(fr.y)}" x2="{_f(x)}" y2="{_f(fr.y - 5)}"/>')
        g.append(f'<line x1="{_f(x)}" y1="{_f(fr.y + fr.h)}" x2="{_f(x)}" y2="{_f(fr.y + fr.h + 5)}"/>')
    for y in z.row_edges[1:-1]:
        g.append(f'<line x1="{_f(fr.x)}" y1="{_f(y)}" x2="{_f(fr.x - 5)}" y2="{_f(y)}"/>')
        g.append(f'<line x1="{_f(fr.x + fr.w)}" y1="{_f(y)}" x2="{_f(fr.x + fr.w + 5)}" y2="{_f(y)}"/>')
    for i, label in enumerate(z.columns):
        cx = (z.col_edges[i] + z.col_edges[i + 1]) / 2
        g.append(f'<text x="{_f(cx)}" y="{_f(fr.y - 3)}" stroke="none">{label}</text>')
        g.append(f'<text x="{_f(cx)}" y="{_f(fr.y + fr.h + 7)}" stroke="none">{label}</text>')
    for i, label in enumerate(z.rows):
        cy = (z.row_edges[i] + z.row_edges[i + 1]) / 2 + 1.2
        g.append(f'<text x="{_f(fr.x - 7)}" y="{_f(cy)}" stroke="none">{label}</text>')
        g.append(f'<text x="{_f(fr.x + fr.w + 5)}" y="{_f(cy)}" stroke="none">{label}</text>')
    g.append("</g>")
    o.extend(g)

    # --- title block (placeholder; the real one lives in the frontend) -----
    tb = layout.title_block
    method = "FIRST ANGLE (ISO E)" if layout.projection_method == "first_angle" else "THIRD ANGLE (ANSI)"
    o.append(f'<g stroke="#000" stroke-width="{thin}" fill="none">'
             f'<rect x="{_f(tb.x)}" y="{_f(tb.y)}" width="{_f(tb.w)}" height="{_f(tb.h)}" stroke-width="{thick}"/>'
             f'<line x1="{_f(tb.x)}" y1="{_f(tb.y + tb.h / 2)}" x2="{_f(tb.x + tb.w)}" y2="{_f(tb.y + tb.h / 2)}"/>'
             f'<line x1="{_f(tb.x + tb.w * 0.6)}" y1="{_f(tb.y)}" x2="{_f(tb.x + tb.w * 0.6)}" y2="{_f(tb.y + tb.h)}"/>'
             "</g>")
    o.append(f'<g font-size="3.5" fill="#000">'
             f'<text x="{_f(tb.x + 3)}" y="{_f(tb.y + 8)}" font-size="5">{escape(title or "UNTITLED")}</text>'
             f'<text x="{_f(tb.x + 3)}" y="{_f(tb.y + tb.h / 2 + 8)}">AutoDraw 2D — geometry preview</text>'
             f'<text x="{_f(tb.x + tb.w * 0.6 + 3)}" y="{_f(tb.y + 8)}">SCALE {layout.scale_label}</text>'
             f'<text x="{_f(tb.x + tb.w * 0.6 + 3)}" y="{_f(tb.y + tb.h / 2 + 8)}">{method}</text>'
             f'<text x="{_f(tb.x + tb.w * 0.6 + 3)}" y="{_f(tb.y + tb.h / 2 + 14)}">'
             f'{layout.page_format} · mm</text></g>')

    # --- views --------------------------------------------------------------
    for p in layout.placements:
        v = views[p.view]
        s = p.scale
        o.append(f'<g id="view-{p.view}" transform="translate({_f(p.x_offset)} {_f(p.y_offset)}) '
                 f'scale({_f(s)})" fill="none" stroke="#000" stroke-linecap="round" stroke-linejoin="round">')
        if show_tangent and v.tangent.svg_path:
            o.append(f'<path d="{v.tangent.svg_path}" stroke-width="{_f(thin / s)}" stroke="#555"/>')
        if show_hidden and v.hidden.svg_path:
            o.append(f'<path d="{v.hidden.svg_path}" stroke-width="{_f(thin / s)}" '
                     f'stroke-dasharray="{_dash(hidden_dash, s)}"/>')
            if show_tangent and v.tangent_hidden.svg_path:
                o.append(f'<path d="{v.tangent_hidden.svg_path}" stroke-width="{_f(thin / s)}" '
                         f'stroke-dasharray="{_dash(hidden_dash, s)}" stroke="#555"/>')
        if v.visible.svg_path:
            o.append(f'<path d="{v.visible.svg_path}" stroke-width="{_f(thick / s)}"/>')

        if show_centerlines and not v.is_isometric:
            ext = CENTER_OVERSHOOT / s
            cl = [f'<g stroke-width="{_f(thin / s)}" stroke-dasharray="{_dash(center_dash, s)}">']
            for c in v.centerlines:
                (x0, y0), (x1, y1) = c.p0, c.p1
                ln = math.hypot(x1 - x0, y1 - y0) or 1.0
                ux, uy = (x1 - x0) / ln, (y1 - y0) / ln
                cl.append(f'<line x1="{_f(x0 - ux * ext)}" y1="{_f(y0 - uy * ext)}" '
                          f'x2="{_f(x1 + ux * ext)}" y2="{_f(y1 + uy * ext)}"/>')
            for m in v.center_marks:
                arm = m.r + ext
                cl.append(f'<line x1="{_f(m.cx - arm)}" y1="{_f(m.cy)}" x2="{_f(m.cx + arm)}" y2="{_f(m.cy)}"/>')
                cl.append(f'<line x1="{_f(m.cx)}" y1="{_f(m.cy - arm)}" x2="{_f(m.cx)}" y2="{_f(m.cy + arm)}"/>')
            cl.append("</g>")
            o.extend(cl)
        o.append("</g>")

        label = p.view.upper() + (f" ({p.scale_label})" if p.scale != layout.scale else "")
        o.append(f'<text x="{_f(p.rect.x + p.rect.w / 2)}" y="{_f(p.rect.y + p.rect.h + 8)}" '
                 f'font-size="3.5" text-anchor="middle" fill="#888">{label}</text>')

    for i, w in enumerate(layout.warnings):
        o.append(f'<text x="{_f(fr.x + 3)}" y="{_f(fr.y + 6 + i * 5)}" font-size="3.5" fill="#c00">'
                 f'{escape(w)}</text>')
    o.append("</svg>")
    return "\n".join(o)

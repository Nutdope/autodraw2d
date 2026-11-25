"""SheetModel -> SVG / DXF / PDF.

* SVG: true-size (width/height in mm), one <g> per CAD layer.
* DXF: R2010, millimetres, real CAD layers with ISO linetypes and lineweights,
  so it opens cleanly in AutoCAD / SolidWorks / Fusion / Inventor. Dimensions
  are exported as plain geometry + text (not associative DIMENSION entities).
* PDF: the SVG rendered with svglib + reportlab (pure Python, vector, true size).
"""
from __future__ import annotations

import io
import math
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

from .models import DASH, LAYERS, Arc, Circle, Line, Poly, SheetModel, Solid, Text

INK = "#0b1220"
MUTED = "#64748b"
SVG_FONT = "Helvetica, Arial, sans-serif"  # Helvetica first: svglib maps it to the PDF base font


def _n(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------
def _layer_style(m: SheetModel, layer: str) -> str:
    _, linetype, _ = LAYERS[layer]
    width = m.thick if layer == "VISIBLE" else m.thin
    style = f'stroke="{INK}" stroke-width="{_n(width)}" fill="none" stroke-linecap="round" stroke-linejoin="round"'
    if linetype in DASH:
        style += f' stroke-dasharray="{" ".join(_n(x) for x in DASH[linetype])}"'
        style = style.replace('stroke-linecap="round"', 'stroke-linecap="butt"')
    if layer == "TANGENT":
        style = style.replace(INK, "#555555")
    return style


def _svg_entity(e) -> str:
    w = f' stroke-width="{_n(e.weight)}"' if getattr(e, "weight", None) else ""
    if isinstance(e, Line):
        return f'<line x1="{_n(e.x1)}" y1="{_n(e.y1)}" x2="{_n(e.x2)}" y2="{_n(e.y2)}"{w}/>'
    if isinstance(e, Arc):
        return (f'<path d="M{_n(e.p0[0])} {_n(e.p0[1])}A{_n(e.r)} {_n(e.r)} 0 {e.large} {e.sweep} '
                f'{_n(e.p1[0])} {_n(e.p1[1])}"/>')
    if isinstance(e, Circle):
        return f'<circle cx="{_n(e.cx)}" cy="{_n(e.cy)}" r="{_n(e.r)}"{w}/>'
    if isinstance(e, Poly):
        tag = "polygon" if e.closed else "polyline"
        pts = " ".join(f"{_n(x)},{_n(y)}" for x, y in e.pts)
        return f'<{tag} points="{pts}"{w}/>'
    if isinstance(e, Solid):
        pts = " ".join(f"{_n(x)},{_n(y)}" for x, y in e.pts)
        return f'<polygon points="{pts}" fill="{INK}" stroke="none"/>'
    if isinstance(e, Text):
        attrs = [f'x="{_n(e.x)}"', f'y="{_n(e.y)}"', f'font-size="{_n(e.size)}"', f'fill="{MUTED if e.muted else INK}"',
                 'stroke="none"']
        if e.anchor != "start":
            attrs.append(f'text-anchor="{e.anchor}"')
        if e.bold:
            attrs.append('font-weight="bold"')
        if e.rotation:
            attrs.append(f'transform="rotate({_n(-e.rotation)} {_n(e.x)} {_n(e.y)})"')
        return f"<text {' '.join(attrs)}>{escape(e.text)}</text>"
    raise TypeError(type(e))


def to_svg(m: SheetModel, title: str = "") -> str:
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_n(m.width)}mm" height="{_n(m.height)}mm" '
        f'viewBox="0 0 {_n(m.width)} {_n(m.height)}" font-family="{SVG_FONT}">',
        f"<title>{escape(title)}</title>" if title else "",
        f'<rect width="{_n(m.width)}" height="{_n(m.height)}" fill="#ffffff"/>',
    ]
    for layer in LAYERS:
        ents = [e for e in m.entities if e.layer == layer]
        if ents:
            out.append(f'<g id="{layer}" {_layer_style(m, layer)}>')
            out.extend(_svg_entity(e) for e in ents)
            out.append("</g>")
    out.append("</svg>")
    return "\n".join(x for x in out if x)


# ---------------------------------------------------------------------------
# DXF
# ---------------------------------------------------------------------------
_LW = (0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90, 100, 106, 120, 140, 158, 200, 211)


def _lineweight(mm: float) -> int:
    v = round(mm * 100)
    return min(_LW, key=lambda x: abs(x - v))


def to_dxf(m: SheetModel) -> bytes:
    import ezdxf
    from ezdxf import units
    from ezdxf.enums import TextEntityAlignment

    doc = ezdxf.new("R2010", setup=False)
    doc.units = units.MM
    doc.header["$MEASUREMENT"] = 1  # metric
    doc.header["$LTSCALE"] = 1.0
    doc.header["$LWDISPLAY"] = 1
    doc.header["$EXTMIN"] = (0, 0, 0)
    doc.header["$EXTMAX"] = (m.width, m.height, 0)

    # ISO 128 patterns in mm: (total length, dash, -gap, ...)
    doc.linetypes.add("DASHED", [4.5, 3.0, -1.5], description="ISO dashed __ __ __")
    doc.linetypes.add("CENTER", [17.5, 12.0, -2.0, 1.5, -2.0], description="ISO chain ____ . ____")
    if "ISO" not in doc.styles:
        doc.styles.new("ISO", dxfattribs={"font": "arial.ttf"})

    for name, (color, linetype, lw) in LAYERS.items():
        if name == "VISIBLE" or name == "BORDER":
            lw = _lineweight(m.thick)
        doc.layers.add(name, color=color, linetype="Continuous" if linetype == "CONTINUOUS" else linetype,
                       lineweight=lw)

    msp = doc.modelspace()
    H = m.height

    def P(x: float, y: float) -> tuple[float, float]:
        return (x, H - y)

    def attrs(e) -> dict:
        a = {"layer": e.layer}
        if getattr(e, "weight", None):
            a["lineweight"] = _lineweight(e.weight)
        return a

    align = {"start": TextEntityAlignment.LEFT, "middle": TextEntityAlignment.CENTER,
             "end": TextEntityAlignment.RIGHT}
    for e in m.entities:
        if isinstance(e, Line):
            msp.add_line(P(e.x1, e.y1), P(e.x2, e.y2), dxfattribs=attrs(e))
        elif isinstance(e, Arc):
            # y-up angles; SVG sweep=1 is clockwise on screen, DXF arcs run CCW.
            a0 = math.degrees(math.atan2(e.cy - e.p0[1], e.p0[0] - e.cx))
            a1 = math.degrees(math.atan2(e.cy - e.p1[1], e.p1[0] - e.cx))
            start, end = (a1, a0) if e.sweep else (a0, a1)
            msp.add_arc(P(e.cx, e.cy), e.r, start, end, dxfattribs=attrs(e))
        elif isinstance(e, Circle):
            msp.add_circle(P(e.cx, e.cy), e.r, dxfattribs=attrs(e))
        elif isinstance(e, Poly):
            msp.add_lwpolyline([P(x, y) for x, y in e.pts], close=e.closed, dxfattribs=attrs(e))
        elif isinstance(e, Solid):
            msp.add_solid([P(x, y) for x, y in e.pts], dxfattribs={"layer": e.layer})
        elif isinstance(e, Text):
            a = {"layer": e.layer, "style": "ISO", "rotation": e.rotation}
            if e.muted:
                a["color"] = 8
            # SVG font-size is the em box; DXF height is the cap height (~0.7 em).
            t = msp.add_text(e.text, height=round(e.size * 0.7, 3), dxfattribs=a)
            t.set_placement(P(e.x, e.y), align=align[e.anchor])

    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def to_pdf(svg: str) -> bytes:
    from reportlab.graphics import renderPDF
    from svglib.svglib import svg2rlg

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sheet.svg"
        path.write_text(svg, encoding="utf-8")
        drawing = svg2rlg(str(path))
    if drawing is None:
        raise RuntimeError("could not convert sheet to PDF")
    return renderPDF.drawToString(drawing)

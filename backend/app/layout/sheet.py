"""Paper formats, ISO 5457 frame/margins, zone grid and title block footprint."""
from __future__ import annotations

import string
from fractions import Fraction

from .models import PageFormat, Rect, Zones

# ISO 216 (short side, long side) in mm
PAGE_SIZES: dict[str, tuple[float, float]] = {
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "A2": (420.0, 594.0),
    "A1": (594.0, 841.0),
}

MARGIN_LEFT = 20.0  # binding margin
MARGIN = 10.0  # top / right / bottom
TITLE_BLOCK_W = 180.0  # ISO 7200 recommended width
TITLE_BLOCK_H = {"A4": 46.0, "A3": 56.0, "A2": 56.0, "A1": 56.0}
ZONE_TARGET = 50.0  # ISO 5457: zones ~50 mm

# Preferred scales, largest first (ISO 5455, plus 1:3 and 1:4, which are common in
# practice and fill the big jump from 1:2 to 1:5). The last two are a safety net for
# very large parts so we never fail to produce a drawing.
STANDARD_SCALES: list[tuple[int, int]] = [
    (5, 1), (2, 1), (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 10), (1, 20), (1, 50), (1, 100),
]


def scale_value(s: tuple[int, int]) -> float:
    return s[0] / s[1]


def scale_label(factor: float) -> str:
    frac = Fraction(factor).limit_denominator(1000)
    if frac >= 1:
        return f"{frac.numerator}:{frac.denominator}"
    inv = Fraction(1) / frac
    if inv.denominator == 1:
        return f"1:{inv.numerator}"
    return f"{frac.numerator}:{frac.denominator}"


def page_dimensions(fmt: PageFormat, orientation: str) -> tuple[float, float]:
    short, long = PAGE_SIZES[fmt]
    return (long, short) if orientation == "landscape" else (short, long)


def frame_rect(width: float, height: float) -> Rect:
    return Rect(x=MARGIN_LEFT, y=MARGIN, w=width - MARGIN_LEFT - MARGIN, h=height - 2 * MARGIN)


def title_block_rect(frame: Rect, fmt: PageFormat) -> Rect:
    w = min(TITLE_BLOCK_W, frame.w)
    h = TITLE_BLOCK_H[fmt]
    return Rect(x=frame.x + frame.w - w, y=frame.y + frame.h - h, w=w, h=h)


def _even_count(length: float) -> int:
    """Even number of zones of roughly ZONE_TARGET mm (ISO 5457)."""
    n = max(2, round(length / ZONE_TARGET))
    if n % 2:
        n = n + 1 if length / (n + 1) >= 40 else max(2, n - 1)
    return n


def zones(frame: Rect) -> Zones:
    nc, nr = _even_count(frame.w), _even_count(frame.h)
    letters = [c for c in string.ascii_uppercase if c not in "IO"]  # ISO skips I and O
    return Zones(
        columns=[str(i + 1) for i in range(nc)],
        rows=letters[:nr],
        col_edges=[round(frame.x + frame.w * i / nc, 3) for i in range(nc + 1)],
        row_edges=[round(frame.y + frame.h * i / nr, 3) for i in range(nr + 1)],
    )

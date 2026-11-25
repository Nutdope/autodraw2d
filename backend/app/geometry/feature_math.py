"""Pure-Python feature helpers (no OpenCascade), shared by the CAD worker and the web
server: number formatting and counterbore pairing work on already-extracted features."""
from __future__ import annotations

from . import vec
from .models import CylinderFeature


def fmt_mm(v: float) -> str:
    """Engineering number format: at least one decimal, at most two."""
    s = f"{v:.2f}"
    if s.endswith("0"):
        s = s[:-1]
    return s


def _coaxial(a: CylinderFeature, b: CylinderFeature) -> bool:
    if abs(vec.dot(a.axis, b.axis)) < 0.9999:
        return False
    rel = vec.sub(b.center, a.center)
    perp = vec.sub(rel, vec.scale(a.axis, vec.dot(rel, a.axis)))
    return vec.norm(perp) < 1e-3


def find_counterbores(features: list[CylinderFeature]) -> dict[str, CylinderFeature]:
    """Map small-hole id -> its counterbore (a larger, blind, coaxial hole sharing an end)."""
    holes = [f for f in features if f.kind == "hole"]
    out: dict[str, CylinderFeature] = {}
    for big in holes:
        if big.through:
            continue
        for small in holes:
            if small.radius >= big.radius - 1e-6 or small.id in out or not _coaxial(big, small):
                continue
            ends_b, ends_s = (big.start, big.end), (small.start, small.end)
            if any(vec.norm(vec.sub(p, q)) < 1e-3 for p in ends_b for q in ends_s):
                out[small.id] = big
    return out

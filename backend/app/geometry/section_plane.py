"""Where a section cuts (no OpenCascade): view axis, plane position and the automatic
depth through the most hole axes. Used by the web server to key the section cache."""
from __future__ import annotations

from collections import Counter

from .models import PartGeometry
from .views import ViewDef


def cut_axis(view: ViewDef) -> tuple[int, float]:
    """(world axis index, sign) of the view direction (toward the viewer)."""
    for i in range(3):
        if abs(abs(view.normal[i]) - 1) < 1e-9:
            return i, (1.0 if view.normal[i] > 0 else -1.0)
    raise ValueError(f"view '{view.name}' is not axis-aligned")


def plane_at(geometry: PartGeometry, view: ViewDef, depth: float) -> float:
    """World coordinate of the cutting plane `depth` mm behind the nearest face."""
    i, s = cut_axis(view)
    return geometry.bbox_max[i] - depth if s > 0 else geometry.bbox_min[i] + depth


def auto_depth(geometry: PartGeometry, view: ViewDef) -> float:
    """Cut through the most hole / boss axes that lie parallel to the plane (the
    section then shows them in true profile); else through the middle."""
    i, s = cut_axis(view)
    size = geometry.size[i]
    eps = max(1e-3, size * 1e-4)
    planes: Counter[float] = Counter()
    for f in geometry.features:
        if f.kind not in ("hole", "boss") or abs(f.axis[i]) > 1e-6:
            continue
        c = f.center[i]
        if geometry.bbox_min[i] + eps < c < geometry.bbox_max[i] - eps:
            planes[round(c, 3)] += 2 if f.kind == "hole" else 1
    if planes:
        mid = (geometry.bbox_min[i] + geometry.bbox_max[i]) / 2
        c = max(planes, key=lambda p: (planes[p], -abs(p - mid)))
    else:
        c = (geometry.bbox_min[i] + geometry.bbox_max[i]) / 2
    return round(geometry.bbox_max[i] - c if s > 0 else c - geometry.bbox_min[i], 4)

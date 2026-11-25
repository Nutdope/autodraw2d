"""Turn untrusted AI output into trusted dimensions.

* every point is snapped onto a known anchor (else the dimension is dropped)
* every value is recomputed from the snapped geometry (the AI's value is ignored)
* every circle callout must sit on a real center mark / arc and gets the
  kernel-derived label unless the AI's label states exactly the same numbers
* free-text notes may not contain numbers the geometry doesn't contain
"""
from __future__ import annotations

import math
import re

from ..geometry.models import PartAnalysis
from .context import ViewCtx
from .gemini import AIAnnotation
from .models import CircleDim, LinearDim

SNAP_TOL = 0.05  # mm, view-local model space
MAX_OFFSET = 20.0  # paper mm: line + text (~4.5 mm) must stay inside the 25 mm view clearance
FIT_CODE = re.compile(r"^[A-Za-z]{1,2}\d{1,2}$")  # H7, h6, js9 ...
NUM = re.compile(r"\d+(?:\.\d+)?")


def _snap(v: ViewCtx, x: float, y: float) -> tuple[float, float] | None:
    best, best_d = None, SNAP_TOL
    for a in v.anchors:
        d = math.hypot(a.x - x, a.y - y)
        if d <= best_d:
            best, best_d = (a.x, a.y), d
    return best


def _numbers(text: str) -> list[float]:
    return [float(n) for n in NUM.findall(text)]


def _label_ok(ai_label: str, truth: str) -> bool:
    return sorted(_numbers(ai_label)) == sorted(_numbers(truth)) and ("THRU" in truth) == ("THRU" in ai_label.upper())


def validate_ai(ai: AIAnnotation, analysis: PartAnalysis, ctx: dict[str, ViewCtx]) -> tuple[list, list[str], int]:
    g = analysis.geometry
    dims: list = []
    rejected = 0
    seen: set = set()
    diameters = {round(f.diameter, 3) for f in g.features if f.kind in ("hole", "boss")}

    for i, d in enumerate(ai.linear):
        v = ctx.get(d.view)
        p1 = _snap(v, d.x1, d.y1) if v else None
        p2 = _snap(v, d.x2, d.y2) if v else None
        if not (v and p1 and p2):
            rejected += 1
            continue
        value = abs(p2[0] - p1[0]) if d.orientation == "horizontal" else abs(p2[1] - p1[1])
        key = (d.view, d.orientation, tuple(sorted((p1, p2))))
        if value < 0.05 or key in seen:
            rejected += 1
            continue
        seen.add(key)
        prefix = "Ø" if d.prefix == "Ø" and round(value, 3) in diameters else ""
        offset = max(-MAX_OFFSET, min(MAX_OFFSET, d.offset_mm))
        if d.offset_from == "edge" and abs(offset) < 4:
            offset = math.copysign(7.0, offset or 1.0)
        tol = d.tolerance_text.strip() if FIT_CODE.match(d.tolerance_text.strip() or "-") else None
        dims.append(LinearDim(
            id=f"AL{i + 1}", view=d.view, x1=p1[0], y1=p1[1], x2=p2[0], y2=p2[1],
            orientation=d.orientation, offset_mm=round(offset, 2), offset_from=d.offset_from,
            value_mm=round(value, 4), prefix=prefix, tolerance_text=tol,
        ))

    def circle_dims(items, kind: str):
        nonlocal rejected
        used_groups: set = set()
        for i, c in enumerate(items):
            v = ctx.get(c.view)
            if not v:
                rejected += 1
                continue
            if kind == "diameter":
                hit = next((m for m in v.vp.center_marks
                            if math.hypot(m.cx - c.cx, m.cy - c.cy) <= SNAP_TOL), None)
                fids = hit.feature_ids if hit else []
                feat = next((f for f in g.features if f.id in fids and abs(f.radius - c.radius) <= 0.01), None) \
                    if hit else None
                if feat is None and hit:  # AI picked the mark but a wrong radius -> use the largest there
                    feat = max((f for f in g.features if f.id in fids), key=lambda f: f.radius, default=None)
                cx, cy = (hit.cx, hit.cy) if hit else (0, 0)
                concave = False
            else:
                hit = next((a for a in v.vp.arc_marks
                            if math.hypot(a.cx - c.cx, a.cy - c.cy) <= SNAP_TOL), None)
                feat = next((f for f in g.features if hit and f.id == hit.feature_id), None)
                cx, cy = (hit.cx, hit.cy) if hit else (0, 0)
                concave = bool(hit and hit.concave)
            if feat is None:
                rejected += 1
                continue
            group = next(fg for fg in g.feature_groups if feat.id in fg.feature_ids)
            if group.label in used_groups:
                rejected += 1
                continue
            used_groups.add(group.label)
            label = c.label_text.strip() if _label_ok(c.label_text, group.label) else group.label
            angle = c.leader_angle_deg % 360
            if kind == "radius" and hit is not None:
                angle = hit.mid_angle_deg  # leader must land on the visible arc
            dims.append(CircleDim(
                type=kind, id=f"A{kind[0].upper()}{i + 1}", view=c.view, cx=cx, cy=cy, radius=feat.radius,
                leader_angle_deg=round(angle, 2), leader_len_mm=12.0 if concave else 10.0, inside=concave,
                label_text=label, feature_ids=group.feature_ids,
            ))

    circle_dims(ai.diameter, "diameter")
    circle_dims(ai.radius, "radius")

    allowed = {round(x, 3) for x in diameters}
    allowed |= {round(f.radius, 3) for f in g.features}
    allowed |= {round(s, 3) for s in g.size}
    notes = []
    for n in ai.notes[:4]:
        text = " ".join(n.upper().split())
        if text and all(round(x, 3) in allowed for x in _numbers(text)) and len(text) <= 80:
            notes.append(text)
    return dims, notes, rejected


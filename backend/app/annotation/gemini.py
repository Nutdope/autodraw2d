"""Gemini structured-output call: the LLM is a *layout* engine, not a measurer.

It sees exact anchors/features and a deterministic baseline, and returns
dimension primitives. Everything it returns goes through validate.py, which
snaps coordinates back onto anchors and recomputes every value/label.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Literal

from pydantic import BaseModel

from ..core.config import settings

log = logging.getLogger("autodraw.gemini")
# overloaded / retired / quota-exhausted -> next model in the list
RETRYABLE = ("503", "UNAVAILABLE", "404", "NOT_FOUND", "429", "RESOURCE_EXHAUSTED")
from ..geometry.features import fmt_mm
from ..geometry.models import PartAnalysis
from .context import ViewCtx
from .deterministic import describe


# --- response schema (kept flat: Gemini's schema subset dislikes unions) ----
class AILinear(BaseModel):
    view: str
    x1: float
    y1: float
    x2: float
    y2: float
    orientation: Literal["horizontal", "vertical"]
    offset_mm: float
    offset_from: Literal["edge", "points"]
    prefix: Literal["none", "Ø"]  # Gemini enums can't contain ""
    value_mm: float
    tolerance_text: str


class AICircle(BaseModel):
    view: str
    cx: float
    cy: float
    radius: float
    leader_angle_deg: float
    label_text: str


class AIAnnotation(BaseModel):
    linear: list[AILinear]
    diameter: list[AICircle]
    radius: list[AICircle]
    notes: list[str]


PROMPT = """You are a senior mechanical drafter placing dimensions on a 2D engineering drawing
(ISO 129-1 / ASME Y14.5 practice). All geometry below was measured exactly by a CAD kernel.

HARD RULES
- Use ONLY coordinates that appear in a view's `anchors`, `circles` or `arcs`. Copy them exactly.
  Never compute, estimate or invent coordinates or measurement values.
- Coordinates are view-local millimetres: origin = top-left of the view, x right, y DOWN.
- value_mm must equal |x2-x1| (horizontal) or |y2-y1| (vertical) of the points you chose.
- Dimension each feature exactly once, in the view where it appears true shape/size.
- Do not dimension the isometric view.

PLACEMENT
- linear.offset_mm is in PAPER mm. Horizontal: positive = above, negative = below.
  Vertical: positive = right, negative = left.
- offset_from "edge": distance from the view's bounding-box edge on that side. Use levels 8, 15, 22
  (at most 3 per side; smaller dimensions closest to the view, overall dimensions outermost).
- offset_from "points" with offset 0: the dimension line is drawn directly between the two points
  (use for diameters across a shaft with prefix "Ø"; otherwise prefix "none").
- Locate holes from datum edges (baseline from the left / bottom edge of the view).
- diameter: one callout per hole group on a circle from `circles`; label like "4x Ø8.0 THRU"
  (copy the group label). radius: callout on an arc from `arcs`, label like "R6.0".
- leader_angle_deg: degrees CCW from +x with y UP; point leaders away from the part (45/135/225/315).
- tolerance_text: "" unless a standard fit code is clearly implied by the feature; never invent numbers.

MODE
- "full": complete functional dimensioning — overall size, every plate thickness / step, every hole
  size and position, every fillet. Remove redundant (double) dimensions.

The `baseline` list is a correct but basic deterministic dimension set; keep what is good, add what
is missing, drop redundancies and fix crowding. notes: up to 4 short UPPERCASE general notes
without numbers (tolerances/units notes are added automatically)."""


def build_payload(analysis: PartAnalysis, ctx: dict[str, ViewCtx], baseline: list) -> dict:
    g = analysis.geometry
    views = []
    for name, v in ctx.items():
        circles = []
        for m in v.vp.center_marks:
            label = next((fg.label for fg in g.feature_groups if set(fg.feature_ids) & set(m.feature_ids)), "")
            circles.append({"cx": m.cx, "cy": m.cy, "r": m.r, "features": m.feature_ids, "group_label": label})
        arcs = []
        for am in v.vp.arc_marks:
            label = next((fg.label for fg in g.feature_groups if am.feature_id in fg.feature_ids), "")
            arcs.append({"cx": am.cx, "cy": am.cy, "r": am.r, "mid_angle_deg": am.mid_angle_deg,
                         "concave": am.concave, "group_label": label})
        views.append({
            "name": name,
            "width": v.w,
            "height": v.h,
            "local_x_is_world": v.signed_axis("x"),
            "local_y_down_is_world": v.signed_axis("y"),
            "anchors": [[a.x, a.y, a.kind] for a in v.anchors],
            "circles": circles,
            "arcs": arcs,
            "centerlines": [[*c.p0, *c.p1] for c in v.vp.centerlines],
        })
    return {
        "mode": "full",
        "part": {
            "size_mm": {"X": g.size[0], "Y": g.size[1], "Z": g.size[2]},
            "feature_groups": [
                {"label": fg.label, "kind": fg.kind, "count": fg.count,
                 "size": fmt_mm(fg.diameter if fg.diameter else (fg.radius or 0))}
                for fg in g.feature_groups
            ],
        },
        "views": views,
        "baseline": [describe(d) for d in baseline],
    }


def call_gemini(payload: dict) -> tuple[AIAnnotation, str]:
    """Returns (parsed annotation, model used).

    Falls through the model list when a model is overloaded (503), retired (404) or out of
    quota (429). Free-tier quotas are per model, so a lighter model often still has calls left.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(timeout=90_000))
    contents = [PROMPT, "INPUT JSON:\n" + json.dumps(payload, separators=(",", ":"))]
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=AIAnnotation,
        temperature=0.2,
    )
    models = list(dict.fromkeys([settings.gemini_model, *settings.gemini_fallback_models]))
    last_exc: Exception | None = None
    for attempt in range(2):
        overloaded: list[str] = []
        for model in models:
            try:
                resp = client.models.generate_content(model=model, contents=contents, config=config)
            except Exception as exc:
                msg = str(exc)
                if not any(code in msg for code in RETRYABLE):
                    raise
                log.info("Gemini model %s unavailable (%s), trying next", model, msg[:60])
                last_exc = exc
                if "503" in msg or "UNAVAILABLE" in msg:
                    overloaded.append(model)
                continue
            if isinstance(resp.parsed, AIAnnotation):
                return resp.parsed, model
            if not resp.text:
                raise RuntimeError("empty response from Gemini")
            return AIAnnotation.model_validate_json(resp.text), model
        # Overload spikes are short: one more pass over just the overloaded models.
        if attempt == 0 and overloaded:
            models = overloaded
            time.sleep(4)
        else:
            break
    raise last_exc or RuntimeError("no Gemini model available")

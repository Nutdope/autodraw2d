"""Annotation orchestration.

Resolution order for mode "full":
  1. pre-computed sample JSON shipped in the repo        (0 API calls; samples never call the API)
  2. per-part AI cache on disk                            (0 API calls)
  3. use_ai=False                -> deterministic          (no quota spent on view toggles)
  4. no GEMINI_API_KEY           -> deterministic + reason
  5. per-IP AI quota exhausted   -> deterministic + reason
  6. Gemini call -> validate     -> on any error / empty result: deterministic + reason

"none" / "overall" / "key" are always deterministic: instant and exact.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from limits import parse
from pydantic import BaseModel

from samples.registry import PARTS_DIR

from ..core.config import settings
from ..core.rate_limit import limiter
from ..geometry.models import PartAnalysis
from .context import build_contexts
from .deterministic import base_notes, deterministic_dimensions
from .gemini import build_payload, call_gemini
from .models import AnnotateRequest, AnnotationSet, CircleDim, Dimension
from .validate import validate_ai

log = logging.getLogger("autodraw.annotation")
PRECOMPUTED_DIR = PARTS_DIR.parent / "annotations"
_AI_LIMIT = parse(settings.ai_rate_limit)
MIN_AI_COVERAGE = 0.5  # AI must keep at least half as many linear dims as the baseline


class CachedAI(BaseModel):
    """What we persist for an AI run (notes are re-derived on serve so tolerance edits apply)."""

    views: list[str]
    dimensions: list[Dimension]
    ai_notes: list[str]
    model: str
    rejected: int


def views_key(views: list[str]) -> str:
    return "-".join(sorted(views))


def precomputed_path(sample_id: str, views: list[str]) -> Path:
    return PRECOMPUTED_DIR / sample_id / f"full__{views_key(views)}.json"


def _merge_notes(tolerance: str, extra: list[str]) -> list[str]:
    notes = base_notes("full", tolerance)
    covered = ("TOLERANC", "MILLIMET", "SHARP EDGE", "BURR")  # already stated by base notes
    for n in extra:
        if n not in notes and not any(k in n for k in covered):
            notes.append(n)
    return notes[:6]


def _ensure_feature_coverage(dims: list, analysis: PartAnalysis, views: list[str]) -> list:
    """Every hole / fillet group must have a callout even if the AI forgot it."""
    covered = {fid for d in dims if isinstance(d, CircleDim) for fid in d.feature_ids}
    for d in deterministic_dimensions(analysis, views, "key"):
        if isinstance(d, CircleDim) and not covered & set(d.feature_ids):
            dims.append(d)
    return dims


def run_ai(analysis: PartAnalysis, views: list[str]) -> CachedAI:
    """One Gemini round-trip + validation. Raises on API / validation failure."""
    ctx = build_contexts(analysis, views)
    baseline = deterministic_dimensions(analysis, views, "full")
    ai, model = call_gemini(build_payload(analysis, ctx, baseline))
    dims, notes, rejected = validate_ai(ai, analysis, ctx)
    n_lin = sum(d.type == "linear" for d in dims)
    n_base = sum(d.type == "linear" for d in baseline)
    if n_lin < MIN_AI_COVERAGE * n_base:
        # Quality gate: a sparse AI layout is worse than the deterministic one.
        raise ValueError(f"AI layout too sparse ({n_lin} vs {n_base} baseline linear dims, {rejected} rejected)")
    dims = _ensure_feature_coverage(dims, analysis, views)
    return CachedAI(views=views, dimensions=dims, ai_notes=notes, model=model, rejected=rejected)


def _from_cache(c: CachedAI, req: AnnotateRequest, source: str) -> AnnotationSet:
    return AnnotationSet(
        mode="full", views=list(req.ortho_views), source=source,  # type: ignore[arg-type]
        dimensions=c.dimensions, notes=_merge_notes(req.tolerance, c.ai_notes), model=c.model, rejected=c.rejected,
    )


def _deterministic(analysis: PartAnalysis, req: AnnotateRequest, reason: Optional[str] = None) -> AnnotationSet:
    views = list(req.ortho_views)
    return AnnotationSet(
        mode=req.mode, views=views, source="deterministic",
        dimensions=deterministic_dimensions(analysis, views, req.mode),
        notes=base_notes(req.mode, req.tolerance), fallback_reason=reason,
    )


def _load(path: Path) -> Optional[CachedAI]:
    try:
        return CachedAI.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None
    except Exception:
        log.warning("ignoring unreadable annotation cache %s", path)
        return None


def annotate(
    analysis: PartAnalysis,
    part_dir: Path,
    sample_id: Optional[str],
    req: AnnotateRequest,
    client_key: str,
) -> AnnotationSet:
    if req.mode != "full":
        return _deterministic(analysis, req)

    views = list(req.ortho_views)
    if sample_id and (pre := _load(precomputed_path(sample_id, views))):
        return _from_cache(pre, req, "precomputed")
    if sample_id:
        # Built-in samples never spend API quota (public demo); uncovered view sets use the rules.
        return _deterministic(analysis, req, "sample_not_precomputed" if req.use_ai else "ai_not_requested")
    cache_file = part_dir / "annotations" / f"full__{views_key(views)}.json"
    if cached := _load(cache_file):
        return _from_cache(cached, req, "ai_cached")

    if not req.use_ai:
        return _deterministic(analysis, req, "ai_not_requested")
    if not settings.gemini_api_key:
        return _deterministic(analysis, req, "ai_not_configured")
    if not limiter.limiter.hit(_AI_LIMIT, "ai-annotate", client_key):
        return _deterministic(analysis, req, "rate_limited")

    try:
        result = run_ai(analysis, views)
    except Exception as exc:  # quota (429), network, schema, validation...
        log.warning("AI annotation failed: %s", exc)
        msg = str(exc)
        reason = "ai_quota" if "429" in msg or "RESOURCE_EXHAUSTED" in msg else "ai_error"
        return _deterministic(analysis, req, reason)

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(result.model_dump_json(), encoding="utf-8")
    return _from_cache(result, req, "ai")


def ai_remaining(client_key: str) -> int:
    stats = limiter.limiter.get_window_stats(_AI_LIMIT, "ai-annotate", client_key)
    return int(stats.remaining)


def dump_precomputed(sample_id: str, result: CachedAI) -> Path:
    path = precomputed_path(sample_id, result.views)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json.loads(result.model_dump_json()), indent=1, ensure_ascii=False), encoding="utf-8")
    return path

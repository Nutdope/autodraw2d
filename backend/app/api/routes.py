"""HTTP endpoints.

GET  /api/health
GET  /api/samples
POST /api/samples/{sample_id}/load      -> PartOut  (cached, instant after first run)
POST /api/parts                         -> PartOut  (multipart .step upload)
GET  /api/parts/{part_id}               -> PartOut
GET  /api/parts/{part_id}/mesh.stl      -> binary STL for the 3D preview
POST /api/parts/{part_id}/layout        -> SheetLayout (pure Python, ~1 ms)
POST /api/parts/{part_id}/annotate      -> AnnotationSet (deterministic / cached / Gemini)
POST /api/parts/{part_id}/export        -> .svg / .dxf / .pdf file of the user's final sheet
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from slowapi.util import get_remote_address

from samples import SAMPLE_PARTS, sample_path

from ..annotation.models import AnnotateRequest, AnnotationSet
from ..annotation.service import ai_remaining, annotate
from ..core.config import settings
from ..export.models import ExportRequest
from ..export.service import export_filename, export_sheet
from ..core.rate_limit import limiter
from ..geometry.loader import StepImportError
from ..layout import SheetConfig, SheetLayout, compute_layout
from ..services.part_store import PartEntry, PartStore
from .schemas import PartOut, SampleOut, part_out

router = APIRouter(prefix="/api")
store = PartStore(settings.cache_dir / "parts", max_items=settings.memory_cache_items)


def _material_for(entry: PartEntry) -> str | None:
    if entry.sample_id and entry.sample_id in SAMPLE_PARTS:
        return SAMPLE_PARTS[entry.sample_id].default_material
    return None


def _require(part_id: str) -> PartEntry:
    entry = store.get(part_id)
    if entry is None:
        raise HTTPException(404, "part not found (cache may have expired) — please reload it")
    return entry


def load_sample(sample_id: str) -> PartEntry:
    if sample_id not in SAMPLE_PARTS:
        raise HTTPException(404, f"unknown sample '{sample_id}'")
    path = sample_path(sample_id)
    if not path.is_file():
        raise HTTPException(500, "sample file missing on server (run samples.generate_samples)")
    return store.ingest(path.read_bytes(), SAMPLE_PARTS[sample_id].name, "sample", sample_id)


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "ai_configured": bool(settings.gemini_api_key), "ai_model": settings.gemini_model}


@router.get("/samples", response_model=list[SampleOut])
def list_samples() -> list[SampleOut]:
    return [SampleOut(id=s.id, name=s.name, description=s.description,
                      default_material=s.default_material) for s in SAMPLE_PARTS.values()]


@router.post("/samples/{sample_id}/load", response_model=PartOut)
def load_sample_endpoint(sample_id: str) -> PartOut:
    entry = load_sample(sample_id)
    return part_out(entry, _material_for(entry))


@router.post("/parts", response_model=PartOut)
@limiter.limit(settings.upload_rate_limit)
def upload_part(request: Request, file: UploadFile = File(...)) -> PartOut:
    name = Path(file.filename or "part.step").name
    if Path(name).suffix.lower() not in (".step", ".stp"):
        raise HTTPException(400, "only .step / .stp files are supported")
    limit = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"file larger than {settings.max_upload_mb} MB")
    if not data:
        raise HTTPException(400, "empty file")
    try:
        entry = store.ingest(data, Path(name).stem, "upload")
    except StepImportError as exc:
        raise HTTPException(400, str(exc)) from exc
    return part_out(entry)


@router.get("/parts/{part_id}", response_model=PartOut)
def get_part(part_id: str) -> PartOut:
    entry = _require(part_id)
    return part_out(entry, _material_for(entry))


@router.get("/parts/{part_id}/mesh.stl")
def get_mesh(part_id: str) -> FileResponse:
    entry = _require(part_id)
    if not entry.mesh_path.is_file():
        raise HTTPException(404, "mesh not available")
    return FileResponse(entry.mesh_path, media_type="model/stl",
                        headers={"Cache-Control": "public, max-age=86400, immutable"})


@router.post("/parts/{part_id}/layout", response_model=SheetLayout)
def layout(part_id: str, cfg: SheetConfig) -> SheetLayout:
    entry = _require(part_id)
    try:
        return compute_layout(entry.analysis.views, cfg)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/parts/{part_id}/annotate", response_model=AnnotationSet)
def annotate_part(part_id: str, req: AnnotateRequest, request: Request) -> AnnotationSet:
    """AI quota (AI_RATE_LIMIT per IP) is only charged when Gemini is actually called."""
    entry = _require(part_id)
    return annotate(entry.analysis, entry.directory, entry.sample_id, req, get_remote_address(request))


@router.get("/ai/quota")
def ai_quota(request: Request) -> dict:
    return {"per_ip_limit": settings.ai_rate_limit, "daily_limit": settings.ai_daily_limit,
            "remaining": ai_remaining(get_remote_address(request)),
            "configured": bool(settings.gemini_api_key)}


@router.post("/parts/{part_id}/export")
@limiter.limit(settings.export_rate_limit)
def export_part(part_id: str, req: ExportRequest, request: Request) -> Response:
    entry = _require(part_id)
    try:
        data, media = export_sheet(entry.analysis, req)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    name = export_filename(req, entry.name)
    return Response(data, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="{name}"',
        "Access-Control-Expose-Headers": "Content-Disposition",
    })

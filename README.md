# AutoDraw 2D

3D CAD (`.step`) → annotated 2D technical drawing. Geometry is computed
deterministically with OpenCascade (`build123d`); an LLM is only ever used to
*place* dimensions on numbers the kernel already computed.

## Repository layout

```
.
├── backend/                      FastAPI + build123d (Docker → Railway/Render/Fly)
│   ├── app/
│   │   ├── geometry/             deterministic CAD kernel layer (OCC only lives here)
│   │   │   ├── loader.py         STEP import + validation
│   │   │   ├── features.py       bbox, mass props, cylinders (holes/bosses/fillets), THRU detection
│   │   │   ├── projection.py     HLR → exact line/arc/circle primitives + SVG paths per layer
│   │   │   ├── views.py          camera definitions (front/top/…/isometric)
│   │   │   ├── mesh.py           STL preview for the 3D widget
│   │   │   ├── models.py         pydantic schemas (single source of truth)
│   │   │   └── vec.py, topo.py   small helpers
│   │   ├── layout/               pure-Python sheet engine (no OCC → instant re-layout)
│   │   │   ├── sheet.py          ISO 216 formats, ISO 5457 frame/zones, title block, scales
│   │   │   ├── placement.py      1st/3rd-angle arrangement, auto-fit scale, iso corner
│   │   │   └── models.py         SheetConfig (validated input) + SheetLayout
│   │   ├── annotation/           dimensioning: deterministic rules, Gemini layout, validator, service
│   │   ├── export/               paper-space sheet model → layered DXF / PDF / SVG writers
│   │   ├── api/                  FastAPI routes + response schemas
│   │   ├── services/part_store.py content-addressed part cache
│   │   ├── core/                 settings (.env) + rate limiter
│   │   ├── pipeline.py           STEP → PartAnalysis orchestration
│   │   └── main.py               FastAPI app
│   ├── samples/                  demo parts, generator, pre-computed AI annotations
│   ├── scripts/                  cli_test.py (304 checks), precompute_annotations.py
│   ├── Dockerfile
│   └── requirements.txt
└── frontend/                     React 18 + Vite + TS + Tailwind (→ Vercel)
```

## Coordinate conventions

* World: mm, **Z up**, the part's front faces **-Y**.
* View-local geometry (everything in a `ViewProjection`): mm at 1:1, origin at the
  top-left of the view's bounding box, **y down** — ready for SVG.
* Sheet: paper mm, origin top-left. Place a view with
  `translate(x_offset, y_offset) scale(scale)`.

## Milestone 1 — run the geometry proof-of-concept (Windows / PowerShell)

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m samples.generate_samples
python -m scripts.cli_test
```

## Milestone 2 — run the web app

Terminal 1 (backend, from `backend/` with the venv active):

```powershell
uvicorn app.main:app --reload --port 8000
```

Terminal 2 (frontend):

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Copy `frontend/.env.example` → `frontend/.env.local`
to point `VITE_API_URL` at a deployed backend.

### API

| Method | Path | Purpose |
|---|---|---|
| GET  | `/api/health` | liveness + whether Gemini is configured |
| GET  | `/api/samples` | built-in sample parts |
| POST | `/api/samples/{id}/load` | analyse (cached) a sample → part + all view projections |
| POST | `/api/parts` | upload `.step` (multipart, 25 MB, rate-limited) |
| GET  | `/api/parts/{id}/mesh.stl` | 3D preview mesh |
| POST | `/api/parts/{id}/layout` | `SheetConfig` → `SheetLayout` (pure Python, ~1 ms) |

| POST | `/api/parts/{id}/annotate` | dimensions: deterministic / cached / Gemini (see below) |
| GET  | `/api/ai/quota` | remaining AI calls for this IP |

## Milestone 3 — dimensioning

The LLM never measures. The pipeline is:

1. **Kernel** extracts exact features + per-view *anchors* (corners, vertices,
   hole centres/quadrants, arc centres, axis ends).
2. **Deterministic dimensioner** (`app/annotation/deterministic.py`) produces a
   correct baseline: hole callouts + datum positions, shaft Ø/step chains,
   fillet radii, plate thicknesses, overall L×W×H, stacked at 8/15/22 mm.
3. **Gemini** (structured JSON output) receives the anchors and baseline and returns
   an improved layout.
4. **Validator** (`app/annotation/validate.py`) snaps every AI point onto an anchor
   (else drops it), recomputes every value, regenerates any callout label whose
   numbers disagree with the kernel, and strips invented numbers from notes.

AI is only spent on an explicit **Auto-Dimension (AI)** click, limited to
`AI_RATE_LIMIT` per IP (default 5/hour). Results are cached per part and view set;
built-in samples ship pre-computed results in `backend/samples/annotations/`
(regenerate with `python -m scripts.precompute_annotations`). If the key is missing,
the quota is hit or Gemini errors, the deterministic set is used and the UI shows a
non-blocking toast. Dimension labels can be dragged (snaps to 2.5 mm with Grid on);
double-click resets one.

Parts are content-addressed (sha256), so the expensive OCC work runs once per
file; every sheet/view change only re-runs the layout endpoint.

---

Milestone 1 output lands in `backend/out/`: `*.analysis.json`, `*.stl`, and one preview
sheet `*.svg` per configuration — open the SVGs in a browser to eyeball them.

## Milestone 4 — export

`POST /api/parts/{id}/export` takes the sheet config, display toggles, title
block and the **final on-screen dimensions** (drag overrides applied) and returns:

| Format | Notes |
|---|---|
| **DXF** (R2010, mm) | CAD layers `VISIBLE` · `HIDDEN` (DASHED) · `CENTERLINES` (CENTER) · `DIMENSIONS` · `BORDER` · `TITLE_BLOCK` (+ `TANGENT`), ISO lineweights. Opens in AutoCAD, SolidWorks (import into a drawing), Fusion, Inventor. Dimensions are plain geometry + text, not associative DIMENSION entities. |
| **PDF** | true-size vector sheet (svglib + reportlab, no native deps) |
| **SVG** | true-size, one `<g>` per layer |

All three render the same paper-space sheet model (`app/export/builder.py`), so
they always match each other and the canvas.

## Deployment

### Backend → Railway / Render / Fly.io (Docker)

```powershell
docker build -t autodraw-backend ./backend
```

```powershell
docker run -p 8000:8000 --env-file backend/.env autodraw-backend
```

On the platform: point it at `backend/Dockerfile` (root directory `backend`),
and set these environment variables (never commit `.env`):

| Variable | Example |
|---|---|
| `GEMINI_API_KEY` | your key (optional — without it everything falls back to rule-based dimensions) |
| `CORS_ORIGINS` | `https://autodraw.yourdomain.com` (your Vercel URL, comma-separated list) |
| `AI_RATE_LIMIT` / `AI_DAILY_LIMIT` | `5/hour` / `50/day` |
| `GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS` | see `backend/.env.example` |

The platform's `$PORT` is honoured. Give the service ≥ 1 GB RAM: the OpenCascade
kernel plus HLR on larger parts does not fit in 512 MB free tiers comfortably.
Rate-limit counters and the part cache are in-memory / ephemeral per instance.

### Frontend → Vercel

Import the repo, set **Root Directory** to `frontend` (framework: Vite), and add:

| Variable | Example |
|---|---|
| `VITE_API_URL` | `https://autodraw-api.up.railway.app` |
| `VITE_PORTFOLIO_URL` | your portfolio URL (shows "← Back to Portfolio") |

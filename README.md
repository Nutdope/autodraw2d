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
│   │   ├── rendering/svg_sheet.py  server-side SVG sheet (CLI preview; base of exports)
│   │   ├── pipeline.py           STEP → PartAnalysis orchestration
│   │   ├── api/                  (M2) FastAPI routers
│   │   ├── annotation/           (M3) Gemini + deterministic auto-dimensioner
│   │   └── export/               (M4) DXF / PDF / SVG
│   ├── samples/                  built-in demo parts + generator
│   ├── scripts/cli_test.py       Milestone 1 verification
│   └── requirements.txt
└── frontend/                     (M2) React 18 + Vite + TS + Tailwind (→ Vercel)
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

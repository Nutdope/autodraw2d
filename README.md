# AutoDraw 2D

**AutoDraw 2D** is an interactive web application that automatically transforms 3D CAD models (`.STEP` / `.STP`) into clean, annotated, manufacturing-ready 2D technical drawings—complete with orthographic projections, automated dimensioning, standard title blocks, and CAD-ready `.DXF` export[cite: 1].

---

## What It Does

* **Instant 3D-to-2D Orthographic Projection:** Upload a 3D `.STEP` part—or explore built-in sample parts (such as a base plate, mounting bracket, and stepped shaft)—and automatically generate multi-view orthographic projections (Front, Top, Right, Left, Rear, Bottom) with hidden line visibility and projection standard controls[cite: 1].
* **Interactive 3D Part Preview:** Inspect your uploaded or sample 3D model directly in the browser alongside your generated 2D layout[cite: 1].
* **Automated Feature Recognition & Smart Dimensioning:** Automatically detects geometric features (holes, fillets, chamfers, steps, and overall bounding dimensions) and places engineering dimensions onto the drawing using a hybrid deterministic + AI-assisted (Gemini) annotation pipeline[cite: 1].
* **Interactive Drawing Sheet & Canvas:** Pan, zoom, inspect, and customize your 2D engineering sheet in real time. Adjust active views, sheet layout placement, dimension styles, projection symbols, and customizable title block metadata directly from the sidebar and top toolbar[cite: 1].
* **CAD-Ready Export:** Export your finalized technical drawing cleanly as a `.DXF` file ready to open in AutoCAD, SolidWorks, Fusion, or any standard 2D CAD tool[cite: 1].

---

## How It Works

1. **Upload or Select a Part:** Drop in a `.STEP` file or choose one of the preloaded mechanical sample parts to inspect it in the 3D previewer[cite: 1].
2. **Configure Views & Layout:** Pick which orthographic views to include on the drawing sheet and let the layout engine automatically arrange and scale them[cite: 1].
3. **Generate & Refine Annotations:** Automatically extract geometric features and apply clean dimensions, then fine-tune title block details and drawing preferences on the interactive canvas[cite: 1].
4. **Export to `.DXF`:** Download the complete 2D engineering drawing with properly structured geometry, dimensions, and title block layers[cite: 1].

---

## Tech Stack

* **Frontend:** React, TypeScript, Vite (interactive SVG/Canvas 2D drawing sheet, 3D part previewer, real-time layout & annotation state synchronization)[cite: 1]
* **Backend:** Python, FastAPI (3D B-Rep geometry loading, feature recognition, orthographic projection, automated sheet placement, and `.DXF` generation)[cite: 1]
* **Annotation Engine:** Deterministic geometric dimensioning paired with Google Gemini AI validation and contextual placement[cite: 1]
* **Deployment:** Vercel (Frontend) & Render / Docker (Backend)[cite: 1]

---

## Project Structure

```text
autodraw2d/
├── frontend/               # React + TypeScript + Vite web interface
│   └── src/
│       ├── api/            # Typed API client & request/response schemas
│       ├── components/     # Drawing canvas, sheet, title block, 3D preview, sidebar & toolbar
│       └── state/          # Application state store & layout/annotation sync hooks
├── backend/                # Python FastAPI geometry, annotation & export engine
│   ├── app/
│   │   ├── api/            # REST endpoints & Pydantic schemas
│   │   ├── geometry/       # STEP loader, feature recognition, orthographic projection
│   │   ├── layout/         # Sheet sizing & automated view placement
│   │   ├── annotation/     # Deterministic + Gemini AI dimensioning & validation
│   │   └── export/         # DXF drawing builder & file writers
│   ├── samples/            # Sample STEP parts & precomputed annotation sets
│   └── scripts/            # CLI testing & cache precomputation utilities
└── render.yaml             # Backend deployment configuration
```

---

## Local Development

### Prerequisites
* **Node.js** (v18+)
* **Python** (v3.10+)
* A **Gemini API key** (optional, for AI-assisted annotation refinement)[cite: 1]
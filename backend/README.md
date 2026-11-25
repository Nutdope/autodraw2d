---
title: AutoDraw 2D API
emoji: 📐
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
short_description: STEP → annotated 2D technical drawing (FastAPI + OpenCascade)
---

# AutoDraw 2D — backend API

FastAPI service behind [AutoDraw 2D](https://github.com/Nutdope/autodraw2d): imports a
`.step` file, computes exact geometry and hidden-line views with OpenCascade
(`build123d`), lays out an ISO/ANSI drawing sheet, dimensions it (rule-based +
optional Gemini layout) and exports layered DXF / PDF / SVG.

This folder is deployed as a Hugging Face **Docker Space**. The block at the top of
this file is the Space configuration; the GitHub Action
`.github/workflows/deploy-huggingface.yml` pushes this folder to the Space on every
change.

Health check: `GET /api/health` · Interactive API docs: `/docs`

Configuration comes from environment variables (Space → Settings → Variables and
secrets); see `.env.example`.

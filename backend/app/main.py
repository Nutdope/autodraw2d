"""FastAPI application entry point.

Dev:   uvicorn app.main:app --reload --port 8000      (from backend/)
"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from samples import SAMPLE_PARTS

from .api.routes import load_sample, router
from .core.config import settings
from .core.rate_limit import limiter

log = logging.getLogger("autodraw")


def _warm_samples() -> None:
    for sample_id in SAMPLE_PARTS:
        try:
            load_sample(sample_id)
            log.info("warmed sample %s", sample_id)
        except Exception:  # never block startup on a sample
            log.exception("failed to warm sample %s", sample_id)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.warm_samples:
        threading.Thread(target=_warm_samples, daemon=True).start()
    yield


app = FastAPI(title="AutoDraw 2D API", version="0.2.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(router)

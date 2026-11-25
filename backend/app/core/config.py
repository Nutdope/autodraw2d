"""Runtime settings from environment variables (and backend/.env if present)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")


def _list(name: str, default: str) -> list[str]:
    return [s.strip() for s in os.getenv(name, default).split(",") if s.strip()]


@dataclass(frozen=True)
class Settings:
    cors_origins: list[str] = field(
        default_factory=lambda: _list("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    )
    cache_dir: Path = Path(os.getenv("CACHE_DIR", str(BACKEND_DIR / "cache")))
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "25"))
    upload_rate_limit: str = os.getenv("UPLOAD_RATE_LIMIT", "20/hour")
    ai_rate_limit: str = os.getenv("AI_RATE_LIMIT", "5/hour")
    memory_cache_items: int = int(os.getenv("MEMORY_CACHE_ITEMS", "24"))
    warm_samples: bool = os.getenv("WARM_SAMPLES", "1") == "1"
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    # Tried in order when the primary model is overloaded (503) or retired (404).
    gemini_fallback_models: list[str] = field(
        default_factory=lambda: _list("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash,gemini-3.5-flash-lite")
    )


settings = Settings()

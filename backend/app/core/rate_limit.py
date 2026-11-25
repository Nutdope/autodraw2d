"""Shared slowapi limiter (per client IP).

Behind a proxy (Railway/Render/Fly) run uvicorn with --proxy-headers so the
real client IP from X-Forwarded-For is used.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

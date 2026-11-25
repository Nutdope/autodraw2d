"""Tiny dependency-free 3D vector helpers (tuples of floats)."""
from __future__ import annotations

import math

Vec3 = tuple[float, float, float]


def add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a: Vec3, k: float) -> Vec3:
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def norm(a: Vec3) -> float:
    return math.sqrt(dot(a, a))


def normalize(a: Vec3) -> Vec3:
    n = norm(a)
    if n < 1e-15:
        raise ValueError("cannot normalize a zero vector")
    return scale(a, 1.0 / n)


def canonical_direction(d: Vec3) -> tuple[Vec3, float]:
    """Return (dc, sign) with d == sign * dc and dc's first non-zero component > 0.

    Lets us treat +axis and -axis as the same line direction when grouping.
    """
    for c in d:
        if abs(c) > 1e-9:
            sign = 1.0 if c > 0 else -1.0
            return scale(d, sign), sign
    return d, 1.0


def clean(x: float, nd: int = 6) -> float:
    """Round and kill negative zero so values are stable as dict keys / JSON."""
    return round(x, nd) + 0.0


def clean3(v: Vec3, nd: int = 6) -> Vec3:
    return (clean(v[0], nd), clean(v[1], nd), clean(v[2], nd))

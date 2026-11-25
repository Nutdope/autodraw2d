"""Camera definitions for the standard drawing views.

World convention (build123d default): Z is up, the part's *front* faces -Y.

Each view is an orthographic camera described by:
  * ``normal`` – unit vector pointing from the part TOWARD the viewer
  * ``up``     – world direction that appears "up" on the sheet

The 2D projected coordinate frame is right-handed on the sheet:
  x_dir = normalize(up × normal),   y_dir = normal × x_dir

The *content* of each view is identical for ISO (first-angle) and ANSI
(third-angle); only the placement on the sheet differs (see layout.placement).
Shared axes guarantee alignment: front/top/bottom share world X as sheet-x,
front/left/right/rear share world Z as sheet-y.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from . import vec

OrthoViewName = Literal["front", "top", "bottom", "left", "right", "rear"]
ViewName = Literal["front", "top", "bottom", "left", "right", "rear", "isometric"]

ORTHO_VIEWS: tuple[str, ...] = ("front", "top", "bottom", "left", "right", "rear")
ALL_VIEWS: tuple[str, ...] = ORTHO_VIEWS + ("isometric",)


@dataclass(frozen=True)
class ViewDef:
    name: str
    normal: vec.Vec3
    up: vec.Vec3
    x_dir: vec.Vec3 = field(init=False)
    y_dir: vec.Vec3 = field(init=False)

    def __post_init__(self) -> None:
        n = vec.normalize(self.normal)
        x = vec.normalize(vec.cross(self.up, n))
        y = vec.cross(n, x)
        object.__setattr__(self, "normal", n)
        object.__setattr__(self, "x_dir", x)
        object.__setattr__(self, "y_dir", y)

    @property
    def is_isometric(self) -> bool:
        return self.name == "isometric"

    def project(self, p: vec.Vec3) -> tuple[float, float]:
        """World point -> projected 2D (y-up) coordinates of this view."""
        return (vec.dot(p, self.x_dir), vec.dot(p, self.y_dir))


_ISO_DIR = (1 / math.sqrt(3), -1 / math.sqrt(3), 1 / math.sqrt(3))  # front-right-top

VIEW_DEFS: dict[str, ViewDef] = {
    "front": ViewDef("front", (0, -1, 0), (0, 0, 1)),
    "rear": ViewDef("rear", (0, 1, 0), (0, 0, 1)),
    "top": ViewDef("top", (0, 0, 1), (0, 1, 0)),
    "bottom": ViewDef("bottom", (0, 0, -1), (0, -1, 0)),
    "right": ViewDef("right", (1, 0, 0), (0, 0, 1)),
    "left": ViewDef("left", (-1, 0, 0), (0, 0, 1)),
    "isometric": ViewDef("isometric", _ISO_DIR, (0, 0, 1)),
}

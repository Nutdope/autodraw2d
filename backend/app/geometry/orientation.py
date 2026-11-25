"""Model orientation: which way is "up" and which side is the front.

AutoDraw's drawing convention is Z up, front facing -Y. CAD systems disagree:
SolidWorks, Inventor, Creo and Fusion export Y-up models, so a bracket that
stands upright in SolidWorks arrives lying on its back. We detect the
originating system from the STEP header (a good default) and let the user
override the up axis and turn the part about it in 90° steps.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Literal, Optional

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:  # OpenCascade is only loaded in the CAD worker process
    from OCP.gp import gp_Trsf
    from OCP.TopoDS import TopoDS_Shape

UpAxis = Literal["+Z", "-Z", "+Y", "-Y", "+X", "-X"]
Turn = Literal[0, 90, 180, 270]

# Systems whose default modelling space is Y-up (front view looks along -Z).
_Y_UP_SYSTEMS = ("solidworks", "inventor", "creo", "pro/engineer", "proengineer", "fusion")


class OrientationRequest(BaseModel):
    up: Literal["auto", "+Z", "-Z", "+Y", "-Y", "+X", "-X"] = "auto"
    turn: Turn = 0


class Orientation(BaseModel):
    up: UpAxis = "+Z"
    turn: Turn = 0
    auto: bool = True  # up axis came from header detection
    source_system: Optional[str] = None  # originating CAD system from the STEP header

    @property
    def key(self) -> str:
        """Short, filesystem-safe id, e.g. 'pz0', 'py90'."""
        return f"{'p' if self.up[0] == '+' else 'n'}{self.up[1].lower()}{self.turn}"

    @property
    def is_identity(self) -> bool:
        return self.up == "+Z" and self.turn == 0


DEFAULT = Orientation()


def read_source_system(data: bytes) -> Optional[str]:
    """Originating system / preprocessor from the STEP FILE_NAME header record."""
    head = data[:16384].decode("latin-1", errors="replace")
    m = re.search(r"FILE_NAME\s*\((.*?)\)\s*;", head, re.S | re.I)
    if not m:
        return None
    strings = [s.strip() for s in re.findall(r"'([^']*)'", m.group(1))]
    # FILE_NAME(name, time, (author), (org), preprocessor_version, originating_system, authorisation)
    tail = [s for s in strings[2:] if s and s.lower() not in ("unknown", "author", "")]
    return " / ".join(dict.fromkeys(tail)) or None


def detect_up(data: bytes) -> tuple[UpAxis, Optional[str]]:
    system = read_source_system(data)
    s = (system or "").lower()
    return ("+Y" if any(k in s for k in _Y_UP_SYSTEMS) else "+Z"), system


def resolve(req: OrientationRequest, data: bytes) -> Orientation:
    detected, system = detect_up(data)
    if req.up == "auto":
        return Orientation(up=detected, turn=req.turn, auto=True, source_system=system)
    return Orientation(up=req.up, turn=req.turn, auto=False, source_system=system)


def _rot(axis: tuple[float, float, float], degrees: float) -> gp_Trsf:
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf

    t = gp_Trsf()
    t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(*axis)), math.radians(degrees))
    return t


# Rotation taking the model's up axis onto +Z (front then faces -Y)
_UP_TO_Z: dict[str, tuple[tuple[float, float, float], float]] = {
    "+Z": ((1, 0, 0), 0.0),
    "-Z": ((1, 0, 0), 180.0),
    "+Y": ((1, 0, 0), 90.0),  # (x, y, z) -> (x, -z, y): Y-up model's front (+Z) faces -Y
    "-Y": ((1, 0, 0), -90.0),
    "+X": ((0, 1, 0), -90.0),
    "-X": ((0, 1, 0), 90.0),
}


def transform_for(o: Orientation) -> gp_Trsf:
    from OCP.gp import gp_Trsf

    axis, deg = _UP_TO_Z[o.up]
    total = _rot((0, 0, 1), o.turn)  # turn about the (new) vertical axis, applied last
    total.Multiply(_rot(axis, deg))
    return total


def apply(shape: TopoDS_Shape, o: Orientation) -> TopoDS_Shape:
    """Bake the rotation into the geometry (copy=True) so every downstream
    algorithm (bbox, HLR, classifier, mesh) sees plain, untransformed shapes."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform

    if o.is_identity:
        return shape
    return BRepBuilderAPI_Transform(shape, transform_for(o), True).Shape()


def from_file(path: str | Path, req: OrientationRequest) -> Orientation:
    return resolve(req, Path(path).read_bytes())

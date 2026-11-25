"""Export request + paper-space entity model.

The sheet model is the single source of truth for every export format:
SVG, DXF and PDF all render the same list of entities, so they always agree.
Coordinates are PAPER millimetres, origin top-left, y DOWN (SVG convention);
the DXF writer flips y.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic import BaseModel, Field

from ..annotation.models import Dimension
from ..layout.models import SheetConfig

ExportFormat = Literal["svg", "dxf", "pdf"]

# name -> (ACI colour, linetype, lineweight in 1/100 mm)
LAYERS: dict[str, tuple[int, str, int]] = {
    "VISIBLE": (7, "CONTINUOUS", 50),
    "HIDDEN": (4, "DASHED", 25),
    "TANGENT": (8, "CONTINUOUS", 18),
    "CENTERLINES": (1, "CENTER", 25),
    "DIMENSIONS": (3, "CONTINUOUS", 25),
    "BORDER": (7, "CONTINUOUS", 50),
    "TITLE_BLOCK": (7, "CONTINUOUS", 25),
}
# Paper-mm dash patterns (ISO 128): dash, gap, ...
DASH = {"DASHED": (3.0, 1.5), "CENTER": (12.0, 2.0, 1.5, 2.0)}


class DisplayOptions(BaseModel):
    hidden: bool = True
    centerlines: bool = True
    tangent: bool = False


class TitleFields(BaseModel):
    partName: str = Field("", max_length=120)
    drawingNumber: str = Field("", max_length=60)
    revision: str = Field("", max_length=10)
    material: str = Field("", max_length=60)
    roughness: str = Field("", max_length=30)
    drawnBy: str = Field("", max_length=60)
    date: str = Field("", max_length=20)


class ExportRequest(BaseModel):
    format: ExportFormat
    sheet: SheetConfig
    display: DisplayOptions = DisplayOptions()
    title: TitleFields = TitleFields()
    tolerance: str = Field("ISO 2768-m", max_length=60)
    # Final, user-adjusted dimensions exactly as shown on screen (overrides already applied)
    dimensions: list[Dimension] = Field(default_factory=list, max_length=400)
    notes: list[str] = Field(default_factory=list, max_length=12)


# ---------------------------------------------------------------------------
# Paper-space entities
# ---------------------------------------------------------------------------
@dataclass
class Line:
    layer: str
    x1: float
    y1: float
    x2: float
    y2: float
    weight: Optional[float] = None  # paper mm; None = layer default


@dataclass
class Arc:
    """SVG-style arc: from p0 to p1 around (cx, cy); flags as in the SVG spec (y-down)."""

    layer: str
    cx: float
    cy: float
    r: float
    p0: tuple[float, float]
    p1: tuple[float, float]
    large: int
    sweep: int


@dataclass
class Circle:
    layer: str
    cx: float
    cy: float
    r: float
    weight: Optional[float] = None


@dataclass
class Poly:
    layer: str
    pts: list[tuple[float, float]]
    closed: bool = False
    weight: Optional[float] = None


@dataclass
class Solid:
    """Filled triangle (arrowheads)."""

    layer: str
    pts: list[tuple[float, float]]


@dataclass
class Text:
    layer: str
    x: float
    y: float  # baseline
    text: str
    size: float  # SVG font-size (em) in paper mm
    anchor: Literal["start", "middle", "end"] = "start"
    rotation: float = 0.0  # degrees, visually counter-clockwise
    bold: bool = False
    muted: bool = False  # secondary (grey) labels


Entity = Line | Arc | Circle | Poly | Solid | Text


@dataclass
class SheetModel:
    width: float
    height: float
    thick: float
    thin: float
    entities: list[Entity] = field(default_factory=list)

    def add(self, *ents: Entity) -> None:
        self.entities.extend(ents)

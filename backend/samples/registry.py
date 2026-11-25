"""Metadata for the built-in sample parts.

The API (Milestone 2) serves these as one-click demos; Milestone 3 attaches
pre-computed dimension JSON to them so they cost zero AI calls.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PARTS_DIR = Path(__file__).resolve().parent / "parts"


@dataclass(frozen=True)
class SamplePart:
    id: str
    name: str
    filename: str
    description: str
    default_material: str
    # Deterministic expectations used by scripts/cli_test.py
    expect: dict = field(default_factory=dict)


SAMPLE_PARTS: dict[str, SamplePart] = {
    "mounting_bracket": SamplePart(
        id="mounting_bracket",
        name="Mounting Bracket",
        filename="mounting_bracket.step",
        description="L-bracket 80x50x60, 4x Ø8 base holes, 2x Ø10 wall holes, R6 inner fillet.",
        default_material="S235JR",
        expect={
            "size": (80.0, 50.0, 60.0),
            "holes": [(8.0, 4, True), (10.0, 2, True)],
            "concave_radii": [6.0],
        },
    ),
    "stepped_shaft": SamplePart(
        id="stepped_shaft",
        name="Stepped Shaft",
        filename="stepped_shaft.step",
        description="4-step shaft Ø20/Ø30/Ø24/Ø16, 1mm end chamfers, Ø6 cross hole.",
        default_material="42CrMo4",
        expect={
            "size": (145.0, 30.0, 30.0),
            "holes": [(6.0, 1, True)],
            "bosses": [16.0, 20.0, 24.0, 30.0],
        },
    ),
}


def sample_path(part_id: str) -> Path:
    try:
        return PARTS_DIR / SAMPLE_PARTS[part_id].filename
    except KeyError as exc:
        raise KeyError(f"unknown sample part '{part_id}'") from exc

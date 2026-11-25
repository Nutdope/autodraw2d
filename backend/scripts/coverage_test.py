"""Dimension-completeness check on the samples plus a set of harder test parts.

Run from ``backend/``:
    python -m scripts.coverage_test            # report + exit 1 if any coordinate is left undimensioned
    python -m scripts.coverage_test --before   # also show what the rules alone (no gap filling) miss

For every part and view set (plus the front view in section A-A), the full
deterministic dimension set must tie every
edge position and hole centre to the datum (app.annotation.coverage).
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from build123d import (
    Align,
    Axis,
    Box,
    BuildPart,
    BuildSketch,
    Cylinder,
    Hole,
    Location,
    Locations,
    Mode,
    Plane,
    PolarLocations,
    Rectangle,
    export_step,
    extrude,
    fillet,
)

from app.annotation.coverage import find_gaps
from app.annotation.deterministic import deterministic_dimensions
from app.pipeline import analyze_part, compute_section
from samples import SAMPLE_PARTS, sample_path

VIEW_SETS = [["front", "top", "right"], ["front", "top", "left"], ["front", "right"]]


def pocket_block():
    """Block with a stepped end, an off-centre pocket, 5 holes on 5 x / 4 y positions, a side hole."""
    with BuildPart() as p:
        Box(120, 60, 30, align=(Align.MIN, Align.MIN, Align.MIN))
        with Locations((100, 0, 18)):  # step down at the right end
            Box(20, 60, 12, align=(Align.MIN, Align.MIN, Align.MIN), mode=Mode.SUBTRACT)
        with Locations((35, 15, 20)):  # rectangular pocket
            Box(30, 22, 10, align=(Align.MIN, Align.MIN, Align.MIN), mode=Mode.SUBTRACT)
        with Locations(*[(x, y, 30) for x, y in ((10, 10), (22, 48), (75, 12), (86, 40), (92, 25))]):
            Hole(radius=3)
        with Locations(Location((0, 30, 9), (0, 90, 0))):  # side hole along X, 25 deep
            Cylinder(radius=4, height=50, mode=Mode.SUBTRACT)
    return p.part


def flange():
    """Ø90x12 disc + Ø44x28 hub, Ø22 bore, 6x Ø9 on PCD 68."""
    with BuildPart() as p:
        Cylinder(radius=45, height=12, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations((0, 0, 12)):
            Cylinder(radius=22, height=28, align=(Align.CENTER, Align.CENTER, Align.MIN))
        Cylinder(radius=11, height=100, mode=Mode.SUBTRACT)
        with Locations((0, 0, 12)):
            with PolarLocations(34, 6):
                Hole(radius=4.5, depth=12)
    return p.part


def post_plate():
    """80x60x10 plate with an off-centre Ø16x20 post and R4 vertical corners."""
    with BuildPart() as p:
        Box(80, 60, 10, align=(Align.MIN, Align.MIN, Align.MIN))
        fillet(p.edges().filter_by(Axis.Z), radius=4)
        with Locations((25, 38, 10)):
            Cylinder(radius=8, height=20, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations((60, 20, 10)):
            Hole(radius=5)
    return p.part


def stair_block():
    """Four-step staircase profile with a through slot window."""
    with BuildPart() as p:
        with BuildSketch(Plane.XZ):
            with Locations((0, 0)):
                Rectangle(100, 10, align=(Align.MIN, Align.MIN))
            with Locations((0, 10)):
                Rectangle(75, 12, align=(Align.MIN, Align.MIN))
            with Locations((0, 22)):
                Rectangle(45, 8, align=(Align.MIN, Align.MIN))
            with Locations((0, 30)):
                Rectangle(20, 15, align=(Align.MIN, Align.MIN))
        extrude(amount=-40)
        with Locations((60, 8, 0)):
            Box(18, 24, 50, align=(Align.MIN, Align.MIN, Align.MIN), mode=Mode.SUBTRACT)
    return p.part


TEST_PARTS = {"pocket_block": pocket_block, "flange": flange, "post_plate": post_plate, "stair_block": stair_block}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", action="store_true", help="also report gaps of the rules without gap filling")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="autodraw_cov_"))
    parts: dict[str, Path] = {sid: sample_path(sid) for sid in SAMPLE_PARTS}
    for name, build in TEST_PARTS.items():
        path = tmp / f"{name}.step"
        export_step(build(), str(path))
        parts[name] = path

    failed = 0
    for name, path in parts.items():
        plain = analyze_part(path)
        sec = compute_section(path, plain, "front", None)
        cut = plain.model_copy(update={"views": {**plain.views, "front": sec.projection}})
        for views, a, label in [(v, plain, "") for v in VIEW_SETS] + [(VIEW_SETS[0], cut, " +A-A")]:
            dims = deterministic_dimensions(a, views, "full")
            gaps = find_gaps(a, views, dims)
            tag = f"{name:<17} {'/'.join(views) + label:<23}"
            if args.before:
                raw = deterministic_dimensions(a, views, "full", fill=False)
                miss = find_gaps(a, views, raw)
                print(f"  {tag} rules only: {len(miss):2d} missing "
                      + ", ".join(f"{g.axis}{g.world:g}" for g in miss))
            status = "ok " if not gaps else "GAP"
            print(f"{status} {tag} {len(dims):3d} dims" + ("" if not gaps else "  missing: " + ", ".join(
                f"{g.axis}{g.world:g}" for g in gaps)))
            failed += bool(gaps)
    print(f"\n{failed} part/view combinations with undimensioned coordinates")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

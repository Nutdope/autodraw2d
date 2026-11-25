"""Generate the built-in sample STEP files with build123d.

Run from ``backend/``:
    python -m samples.generate_samples
"""
from __future__ import annotations

from build123d import (
    Align,
    Axis,
    Box,
    BuildPart,
    CounterBoreHole,
    Cylinder,
    GeomType,
    Hole,
    Location,
    Locations,
    Mode,
    chamfer,
    export_step,
    fillet,
)

from .registry import PARTS_DIR, sample_path


def make_mounting_bracket():
    """L-bracket: base plate 80x50x8 + upright wall 80x8x60 at the back (+Y)."""
    base_w, base_d, base_t = 80.0, 50.0, 8.0
    wall_t, wall_h = 8.0, 60.0
    wall_y = base_d - wall_t  # front face of the wall: y = 42

    with BuildPart() as bracket:
        Box(base_w, base_d, base_t, align=(Align.CENTER, Align.MIN, Align.MIN))
        with Locations((0, wall_y, 0)):
            Box(base_w, wall_t, wall_h, align=(Align.CENTER, Align.MIN, Align.MIN))

        # R6 fillet on the inner (concave) corner where base meets wall
        inner = [
            e
            for e in bracket.edges().filter_by(Axis.X)
            if abs(e.center().Y - wall_y) < 1e-6 and abs(e.center().Z - base_t) < 1e-6
        ]
        fillet(inner, radius=6)

        # 4x Ø8 THRU in the base plate, drilled from the top face downward
        with Locations(*[(x, y, base_t) for x in (-28, 28) for y in (12, 30)]):
            Hole(radius=4)

        # 2x Ø10 THRU in the wall (axis along Y)
        with Locations(*[Location((x, wall_y + wall_t / 2, 40), (90, 0, 0)) for x in (-20, 20)]):
            Cylinder(radius=5, height=20, mode=Mode.SUBTRACT)

    return bracket.part


def make_stepped_shaft():
    """Shaft along +X: Ø20x30, Ø30x50, Ø24x40, Ø16x25; 1mm end chamfers; Ø6 cross hole."""
    segments = [(20.0, 30.0), (30.0, 50.0), (24.0, 40.0), (16.0, 25.0)]

    with BuildPart() as shaft:
        x = 0.0
        for dia, length in segments:
            with Locations(Location((x + length / 2, 0, 0), (0, 90, 0))):
                Cylinder(radius=dia / 2, height=length)
            x += length

        circles = shaft.edges().filter_by(GeomType.CIRCLE).group_by(Axis.X)
        chamfer(list(circles[0]) + list(circles[-1]), length=1)

        # Ø6 cross hole through the Ø30 collar (axis along Z)
        with Locations((55, 0, 0)):
            Cylinder(radius=3, height=40, mode=Mode.SUBTRACT)

    return shaft.part


def make_base_plate():
    """100x60x12 plate: 2x Ø9 THRU with Ø15x4 counterbore, Ø20x8 blind pocket, R5 corners."""
    with BuildPart() as plate:
        Box(100, 60, 12, align=(Align.MIN, Align.MIN, Align.MIN))
        with Locations((20, 30, 12), (80, 30, 12)):
            CounterBoreHole(radius=4.5, counter_bore_radius=7.5, counter_bore_depth=4)
        with Locations((50, 30, 12)):
            Hole(radius=10, depth=8)
        fillet(plate.edges().filter_by(Axis.Z), radius=5)
    return plate.part


BUILDERS = {
    "mounting_bracket": make_mounting_bracket,
    "stepped_shaft": make_stepped_shaft,
    "base_plate": make_base_plate,
}


def main() -> None:
    PARTS_DIR.mkdir(parents=True, exist_ok=True)
    for part_id, build in BUILDERS.items():
        part = build()
        out = sample_path(part_id)
        export_step(part, str(out))
        bb = part.bounding_box()
        print(
            f"[ok] {part_id:<17} -> {out.name}  "
            f"size {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, "
            f"volume {part.volume:,.1f} mm³"
        )


if __name__ == "__main__":
    main()

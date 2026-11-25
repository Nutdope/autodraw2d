"""Milestone 1 proof-of-concept: STEP -> features -> HLR views -> sheet layout.

Run from ``backend/``:
    python -m scripts.cli_test                       # both samples, 3 sheet configs each
    python -m scripts.cli_test --step path/to/part.step --format A2 --standard ANSI

Writes to backend/out/:  <part>.analysis.json, <part>.stl, <part>__<config>.svg
Exits non-zero if any deterministic check fails.
"""
from __future__ import annotations

import argparse
import itertools
import math
import sys
from pathlib import Path

from app.geometry import VIEW_DEFS, vec
from app.geometry.models import PartAnalysis
from app.layout import SheetConfig, SheetLayout, compute_layout
from app.layout.placement import _R
from app.pipeline import analyze_part
from app.rendering.svg_sheet import render_sheet_svg
from samples import SAMPLE_PARTS, sample_path

OUT_DIR = Path(__file__).resolve().parents[1] / "out"

DEFAULT_CONFIGS = [
    SheetConfig(page_format="A3", orientation="landscape", standard="ISO",
                ortho_views=["front", "top", "left"], show_isometric=True),
    SheetConfig(page_format="A4", orientation="landscape", standard="ANSI",
                ortho_views=["front", "top", "right"], show_isometric=True),
    SheetConfig(page_format="A4", orientation="portrait", standard="ISO",
                ortho_views=["front", "right", "bottom"], show_isometric=False),
]


class Checker:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passes = 0

    def check(self, ok: bool, msg: str) -> None:
        if ok:
            self.passes += 1
        else:
            self.failures.append(msg)
            print(f"    FAIL  {msg}")


# ---------------------------------------------------------------------------
# Geometry checks
# ---------------------------------------------------------------------------
def check_projection_extents(a: PartAnalysis, ck: Checker) -> None:
    """Every ortho view's 2D bbox must equal the projected 3D bbox.

    Catches mirrored / mis-oriented HLR output (the samples are not symmetric
    about the origin in X or Y, so a flip would shift the range).
    """
    g = a.geometry
    corners = list(itertools.product(*zip(g.bbox_min, g.bbox_max)))
    tol = max(0.02, 1e-3 * max(g.size))
    for name, v in a.views.items():
        if v.is_isometric:
            continue
        vd = VIEW_DEFS[name]
        xs = [vec.dot(c, vd.x_dir) for c in corners]
        ys = [vec.dot(c, vd.y_dir) for c in corners]
        exp = (min(xs), min(ys), max(xs), max(ys))
        ok = all(abs(e - b) <= tol for e, b in zip(exp, v.bbox))
        ck.check(ok, f"{a.part_name}/{name}: view bbox {v.bbox} != projected part bbox "
                     f"{tuple(round(e, 3) for e in exp)}")
        ck.check(bool(v.visible.primitives), f"{a.part_name}/{name}: no visible edges")


def _svg_arc_center(p0, p1, r, large, sweep):
    """Centre implied by SVG arc flags (SVG 1.1 implementation notes F.6.5)."""
    (x1, y1), (x2, y2) = p0, p1
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    d2 = dx * dx + dy * dy
    f = math.sqrt(max(0.0, (r * r - d2) / d2)) if d2 > 0 else 0.0
    if large == sweep:
        f = -f
    return (f * dy + (x1 + x2) / 2, -f * dx + (y1 + y2) / 2)


def check_arc_flags(a: PartAnalysis, ck: Checker) -> None:
    """Every arc's SVG flags must reproduce its true centre (else it renders mirrored)."""
    for name, v in a.views.items():
        for layer in ("visible", "hidden", "tangent", "tangent_hidden"):
            for p in getattr(v, layer).primitives:
                if p.type == "arc":
                    c = _svg_arc_center(p.p0, p.p1, p.r, p.large, p.sweep)
                    ck.check(math.dist(c, p.c) < 1e-3,
                             f"{a.part_name}/{name}: arc flags give centre {c}, expected {p.c}")


def check_sample_features(a: PartAnalysis, part_id: str, ck: Checker) -> None:
    exp = SAMPLE_PARTS[part_id].expect
    g = a.geometry
    if "size" in exp:
        ck.check(all(abs(s - e) < 0.01 for s, e in zip(g.size, exp["size"])),
                 f"{part_id}: size {g.size} != expected {exp['size']}")
    holes = [x for x in g.feature_groups if x.kind == "hole"]
    for dia, count, thru in exp.get("holes", []):
        match = [h for h in holes if abs(h.diameter - dia) < 1e-3 and h.count == count and h.through == thru]
        ck.check(bool(match), f"{part_id}: expected {count}x Ø{dia} {'THRU' if thru else 'blind'}; "
                              f"got {[h.label for h in holes]}")
    if "bosses" in exp:
        got = sorted(round(f.diameter, 3) for f in g.features if f.kind == "boss")
        ck.check(got == sorted(exp["bosses"]), f"{part_id}: bosses {got} != {exp['bosses']}")
    for r in exp.get("convex_radii", []):
        ck.check(any(f.kind == "convex_arc" and abs(f.radius - r) < 1e-3 for f in g.features),
                 f"{part_id}: missing convex R{r}")
    labels = {fg.label for fg in g.feature_groups}
    for lbl in exp.get("labels", []):
        ck.check(lbl in labels, f"{part_id}: expected callout '{lbl}', got {sorted(labels)}")
    for r in exp.get("concave_radii", []):
        ck.check(any(f.kind == "concave_arc" and abs(f.radius - r) < 1e-3 for f in g.features),
                 f"{part_id}: missing concave R{r}")


# ---------------------------------------------------------------------------
# Layout checks
# ---------------------------------------------------------------------------
def check_layout(a: PartAnalysis, lay: SheetLayout, tag: str, ck: Checker) -> None:
    fr = _R.of(lay.frame)
    tb = _R.of(lay.title_block)
    rects = {p.view: _R.of(p.rect) for p in lay.placements}
    ck.check(lay.fits, f"{tag}: layout does not fit ({lay.warnings})")
    for name, r in rects.items():
        ck.check(r.inside(fr), f"{tag}: {name} leaves the frame")
        ck.check(not r.intersects(tb), f"{tag}: {name} overlaps the title block")
    for (n1, r1), (n2, r2) in itertools.combinations(rects.items(), 2):
        ck.check(not r1.inflate(lay.view_clearance / 2).intersects(r2.inflate(lay.view_clearance / 2)),
                 f"{tag}: {n1} and {n2} closer than {lay.view_clearance} mm")

    # Projection alignment: world origin must map to the same sheet x for views in
    # the front column, and to the same sheet y for views in the front row.
    place = {p.view: p for p in lay.placements}

    def origin_x(n):  # sheet x of projected x = 0
        p, v = place[n], a.views[n]
        return p.x_offset - v.bbox[0] * p.scale

    def origin_y(n):  # sheet y of projected y = 0
        p, v = place[n], a.views[n]
        return p.y_offset + v.bbox[3] * p.scale

    col = [n for n in place if place[n].grid_cell and place[n].grid_cell[0] == 0]
    row = [n for n in place if place[n].grid_cell and place[n].grid_cell[1] == 0]
    for n in col[1:]:
        ck.check(math.isclose(origin_x(n), origin_x(col[0]), abs_tol=1e-3),
                 f"{tag}: {n} not vertically aligned with {col[0]}")
    for n in row[1:]:
        ck.check(math.isclose(origin_y(n), origin_y(row[0]), abs_tol=1e-3),
                 f"{tag}: {n} not horizontally aligned with {row[0]}")

    # Projection method: ISO puts the top view BELOW the front, ANSI ABOVE.
    if "top" in place:
        below = place["top"].rect.y > place["front"].rect.y
        ck.check(below == (lay.standard == "ISO"), f"{tag}: top view on wrong side for {lay.standard}")


# ---------------------------------------------------------------------------
def print_summary(a: PartAnalysis) -> None:
    g = a.geometry
    print(f"  size      {g.size[0]:.2f} x {g.size[1]:.2f} x {g.size[2]:.2f} mm   "
          f"volume {g.volume:,.1f} mm³   faces {g.face_count}   solids {g.solid_count}")
    print(f"  COM       ({g.center_of_mass[0]:.2f}, {g.center_of_mass[1]:.2f}, {g.center_of_mass[2]:.2f})")
    print("  features  " + (", ".join(fg.label for fg in g.feature_groups) or "none"))
    print("  views     " + "  ".join(
        f"{n}[{v.width:.1f}x{v.height:.1f} vis={len(v.visible.primitives)} hid={len(v.hidden.primitives)} "
        f"{v.compute_ms:.0f}ms]" for n, v in a.views.items()))
    print(f"  timings   {a.timings_ms}")


def run_part(step: Path, part_id: str | None, configs: list[SheetConfig], ck: Checker) -> None:
    print(f"\n=== {step.name} ===")
    a = analyze_part(step, mesh_out=OUT_DIR / f"{step.stem}.stl")
    print_summary(a)
    (OUT_DIR / f"{step.stem}.analysis.json").write_text(a.model_dump_json(indent=1), encoding="utf-8")

    check_projection_extents(a, ck)
    check_arc_flags(a, ck)
    if part_id:
        check_sample_features(a, part_id, ck)

    for cfg in configs:
        tag = f"{step.stem}__{cfg.page_format}_{cfg.orientation[:4]}_{cfg.standard}"
        lay = compute_layout(a.views, cfg)
        check_layout(a, lay, tag, ck)
        svg = render_sheet_svg(lay, a.views, title=step.stem.replace("_", " ").upper())
        out = OUT_DIR / f"{tag}.svg"
        out.write_text(svg, encoding="utf-8")
        views = ", ".join(f"{p.view}@({p.x_offset:.0f},{p.y_offset:.0f})" for p in lay.placements)
        print(f"  layout    {tag}: scale {lay.scale_label} fits={lay.fits}  {views}")
        for w in lay.warnings:
            print(f"            note: {w}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--step", type=Path, help="custom .step file (default: built-in samples)")
    ap.add_argument("--format", default=None, choices=["A4", "A3", "A2", "A1"])
    ap.add_argument("--orientation", default="landscape", choices=["landscape", "portrait"])
    ap.add_argument("--standard", default="ISO", choices=["ISO", "ANSI"])
    ap.add_argument("--views", default="front,top,right", help="comma list, max 3 ortho views")
    ap.add_argument("--no-iso", action="store_true")
    ap.add_argument("--scale", default="auto")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    configs = DEFAULT_CONFIGS
    if args.format:
        configs = [SheetConfig(page_format=args.format, orientation=args.orientation,
                               standard=args.standard, ortho_views=args.views.split(","),
                               show_isometric=not args.no_iso, scale=args.scale)]

    ck = Checker()
    if args.step:
        run_part(args.step, None, configs, ck)
    else:
        for part_id in SAMPLE_PARTS:
            path = sample_path(part_id)
            if not path.exists():
                print(f"missing {path} — run:  python -m samples.generate_samples")
                return 2
            run_part(path, part_id, configs, ck)

    print(f"\n{ck.passes} checks passed, {len(ck.failures)} failed.  Output: {OUT_DIR}")
    return 1 if ck.failures else 0


if __name__ == "__main__":
    sys.exit(main())

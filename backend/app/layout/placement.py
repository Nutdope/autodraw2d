"""View arrangement + auto-fit scale selection.

Pure Python, no OCC: runs in microseconds, so the API can re-layout on every
page-size / view-toggle change without re-projecting the part.

Arrangement
-----------
Views sit on a grid relative to the front view at (col 0, row 0):

                ANSI (third angle)        ISO (first angle)
    top         above   (row -1)          below  (row +1)
    bottom      below   (row +1)          above  (row -1)
    left        left    (col -1)          right  (col +1)
    right       right   (col +1)          left   (col -1)
    rear        far side of the row (col ±2), next to the side view

Alignment is exact: views in a column share projected X (world X), views in
row 0 share projected Y (world Z), so their sheet positions are derived from
one common origin per column / row rather than from per-view bounding boxes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Optional

from ..geometry.models import ViewProjection
from .models import Rect, SheetConfig, SheetLayout, ViewPlacement
from .sheet import (
    STANDARD_SCALES,
    frame_rect,
    page_dimensions,
    scale_label,
    scale_value,
    title_block_rect,
    zones,
)

VIEW_CLEARANCE = 25.0  # paper mm kept free around every view for dimensions
_EPS = 1e-6


# ---------------------------------------------------------------------------
# Rectangle helper (sheet space, y down)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _R:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @classmethod
    def of(cls, r: Rect) -> "_R":
        return cls(r.x, r.y, r.w, r.h)

    def inflate(self, d: float) -> "_R":
        return _R(self.x - d, self.y - d, self.w + 2 * d, self.h + 2 * d)

    def shift(self, dx: float, dy: float) -> "_R":
        return _R(self.x + dx, self.y + dy, self.w, self.h)

    def intersects(self, o: "_R") -> bool:
        return (self.x < o.right - _EPS and o.x < self.right - _EPS
                and self.y < o.bottom - _EPS and o.y < self.bottom - _EPS)

    def inside(self, o: "_R") -> bool:
        return (self.x >= o.x - _EPS and self.y >= o.y - _EPS
                and self.right <= o.right + _EPS and self.bottom <= o.bottom + _EPS)

    def rect(self) -> Rect:
        return Rect(x=round(self.x, 4), y=round(self.y, 4), w=round(self.w, 4), h=round(self.h, 4))


def _valid(r: _R, avail: _R, blockers: list[_R]) -> bool:
    return r.inside(avail) and not any(r.intersects(b) for b in blockers)


def _max_shift(r: _R, ux: int, uy: int, ok: Callable[[_R], bool], limit: float, step: float = 0.5) -> float:
    n = 0
    while (n + 1) * step <= limit and ok(r.shift(ux * (n + 1) * step, uy * (n + 1) * step)):
        n += 1
    return n * step


def _center(r: _R, avail: _R, blockers: list[_R]) -> _R:
    """Slide a placed rect to the middle of the free space right/below it."""
    ok = lambda rr: _valid(rr, avail, blockers)  # noqa: E731
    r = r.shift(_max_shift(r, 1, 0, ok, avail.w) / 2, 0)
    r = r.shift(0, _max_shift(r, 0, 1, ok, avail.h) / 2)
    return r


# ---------------------------------------------------------------------------
# Orthographic grid
# ---------------------------------------------------------------------------
def ortho_grid(views: list[str], standard: str) -> dict[str, tuple[int, int]]:
    if not views:
        return {}
    third_angle = standard == "ANSI"
    near_side, far_side = ("left", "right") if third_angle else ("right", "left")
    top_row = -1 if third_angle else 1

    grid: dict[str, tuple[int, int]] = {"front": (0, 0)}
    if "top" in views:
        grid["top"] = (0, top_row)
    if "bottom" in views:
        grid["bottom"] = (0, -top_row)
    if near_side in views:
        grid[near_side] = (-1, 0)
    if far_side in views:
        grid[far_side] = (1, 0)
    if "rear" in views:
        if far_side in views:
            grid["rear"] = (2, 0)
        elif near_side in views:
            grid["rear"] = (-2, 0)
        else:
            grid["rear"] = (1, 0)
    return grid


@dataclass
class _GridExtents:
    cols: list[int]
    rows: list[int]
    colmin: dict[int, float]
    colmax: dict[int, float]
    rowmin: dict[int, float]
    rowmax: dict[int, float]


def _grid_extents(grid: dict[str, tuple[int, int]], views: Mapping[str, ViewProjection]) -> _GridExtents:
    colmin: dict[int, float] = {}
    colmax: dict[int, float] = {}
    rowmin: dict[int, float] = {}
    rowmax: dict[int, float] = {}
    for name, (c, r) in grid.items():
        xmin, ymin, xmax, ymax = views[name].bbox
        colmin[c] = min(colmin.get(c, xmin), xmin)
        colmax[c] = max(colmax.get(c, xmax), xmax)
        rowmin[r] = min(rowmin.get(r, ymin), ymin)
        rowmax[r] = max(rowmax.get(r, ymax), ymax)
    return _GridExtents(sorted(colmin), sorted(rowmin), colmin, colmax, rowmin, rowmax)


def _block_size(g: _GridExtents, s: float, gap: float):
    col_x: dict[int, float] = {}
    x = 0.0
    for c in g.cols:
        col_x[c] = x
        x += (g.colmax[c] - g.colmin[c]) * s + gap
    row_y: dict[int, float] = {}
    y = 0.0
    for r in g.rows:
        row_y[r] = y
        y += (g.rowmax[r] - g.rowmin[r]) * s + gap
    return x - gap, y - gap, col_x, row_y


# ---------------------------------------------------------------------------
# Placement search
# ---------------------------------------------------------------------------
def _try_place(
    g: Optional[_GridExtents],
    s: float,
    iso: Optional[ViewProjection],
    si: Optional[float],
    avail: _R,
    blockers: list[_R],
    gap: float,
) -> Optional[tuple[Optional[_R], Optional[_R]]]:
    ortho: Optional[_R] = None
    if g is not None:
        bw, bh, _, _ = _block_size(g, s, gap)
        ortho = _R(avail.x, avail.y, bw, bh)
        if not _valid(ortho, avail, blockers):
            return None

    if iso is None:
        return (_center(ortho, avail, blockers) if ortho else None), None

    wi, hi = iso.width * si, iso.height * si
    if ortho is None:
        r = _R(avail.x, avail.y, wi, hi)
        return (None, _center(r, avail, blockers)) if _valid(r, avail, blockers) else None

    candidates = (
        _R(avail.right - wi, avail.y, wi, hi),  # top-right corner (preferred)
        _R(avail.x, ortho.bottom + gap, wi, hi),  # under the ortho block
        _R(avail.x, avail.bottom - hi, wi, hi),  # bottom-left corner
    )
    for cand in candidates:
        if _valid(cand, avail, blockers + [ortho.inflate(gap)]):
            return _center(ortho, avail, blockers + [cand.inflate(gap)]), cand
    return None


def compute_layout(views: Mapping[str, ViewProjection], cfg: SheetConfig) -> SheetLayout:
    width, height = page_dimensions(cfg.page_format, cfg.orientation)
    frame = frame_rect(width, height)
    tb = title_block_rect(frame, cfg.page_format)
    gap = VIEW_CLEARANCE
    avail = _R(frame.x + gap, frame.y + gap, frame.w - 2 * gap, frame.h - 2 * gap)
    blockers = [_R.of(tb).inflate(gap)]

    needed = list(cfg.ortho_views) + (["isometric"] if cfg.show_isometric else [])
    missing = [v for v in needed if v not in views]
    if missing:
        raise ValueError(f"projections missing for views: {', '.join(missing)}")

    grid = ortho_grid(list(cfg.ortho_views), cfg.standard)
    g = _grid_extents(grid, views) if grid else None
    iso = views["isometric"] if cfg.show_isometric else None

    all_scales = [scale_value(s) for s in STANDARD_SCALES]
    manual = cfg.scale_factor()
    main_candidates = [manual] if manual else all_scales

    warnings: list[str] = []
    found = None
    for s in main_candidates:
        # The iso view may drop ONE step below the main scale; beyond that a smaller
        # sheet scale reads better than a postage-stamp pictorial.
        iso_candidates = ([s] + [x for x in all_scales if x < s][:1]) if iso else [None]
        for si in iso_candidates:
            placed = _try_place(g, s, iso, si, avail, blockers, gap)
            if placed is not None:
                found = (s, si, *placed)
                break
        if found:
            break

    fits = found is not None
    if found:
        s, si, ortho_r, iso_r = found
    else:
        s = manual if manual else all_scales[-1]
        si = s if iso else None
        ortho_r = iso_r = None
        if g is not None:
            bw, bh, _, _ = _block_size(g, s, gap)
            ortho_r = _R(avail.x, avail.y, bw, bh)
        if iso is not None:
            iso_r = _R(avail.right - iso.width * si, avail.y, iso.width * si, iso.height * si)
        warnings.append(
            f"Views do not fit on {cfg.page_format} {cfg.orientation} at {scale_label(s)} "
            "with the required dimension clearance; choose a larger sheet or smaller scale."
        )

    placements: list[ViewPlacement] = []
    if g is not None and ortho_r is not None:
        _, _, col_x, row_y = _block_size(g, s, gap)
        order = ["front"] + [v for v in cfg.ortho_views if v != "front"]
        for name in order:
            c, r = grid[name]
            v = views[name]
            xo = ortho_r.x + col_x[c] + (v.bbox[0] - g.colmin[c]) * s
            yo = ortho_r.y + row_y[r] + (g.rowmax[r] - v.bbox[3]) * s
            placements.append(ViewPlacement(
                view=name, scale=s, scale_label=scale_label(s),
                x_offset=round(xo, 4), y_offset=round(yo, 4),
                rect=_R(xo, yo, v.width * s, v.height * s).rect(),
                grid_cell=(c, r),
            ))
    if iso is not None and iso_r is not None:
        if si != s:
            warnings.append(f"Isometric view drawn at {scale_label(si)} to fit the sheet.")
        placements.append(ViewPlacement(
            view="isometric", scale=si, scale_label=scale_label(si),
            x_offset=round(iso_r.x, 4), y_offset=round(iso_r.y, 4),
            rect=iso_r.rect(), grid_cell=None,
        ))

    return SheetLayout(
        page_format=cfg.page_format,
        orientation=cfg.orientation,
        standard=cfg.standard,
        projection_method="third_angle" if cfg.standard == "ANSI" else "first_angle",
        page_width=width,
        page_height=height,
        frame=frame,
        title_block=tb,
        zones=zones(frame),
        view_clearance=gap,
        scale=s,
        scale_label=scale_label(s),
        auto_scale=manual is None,
        placements=placements,
        fits=fits,
        warnings=warnings,
    )

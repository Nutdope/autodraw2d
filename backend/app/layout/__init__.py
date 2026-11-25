"""Sheet layout: page formats, ISO frame, view arrangement and auto-fit scale."""
from .models import Rect, SheetConfig, SheetLayout, ViewPlacement
from .placement import VIEW_CLEARANCE, compute_layout, ortho_grid

__all__ = [
    "Rect",
    "SheetConfig",
    "SheetLayout",
    "ViewPlacement",
    "VIEW_CLEARANCE",
    "compute_layout",
    "ortho_grid",
]

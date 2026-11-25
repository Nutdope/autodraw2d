"""Small OCP topology helpers."""
from __future__ import annotations

from typing import Iterator

from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS_Shape


def iter_shapes(shape: TopoDS_Shape, kind: TopAbs_ShapeEnum) -> Iterator[TopoDS_Shape]:
    if shape is None or shape.IsNull():
        return
    exp = TopExp_Explorer(shape, kind)
    while exp.More():
        yield exp.Current()
        exp.Next()

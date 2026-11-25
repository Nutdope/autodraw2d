"""Content-addressed cache of analysed parts.

part_id = first 16 hex chars of sha256(step bytes), so re-uploading the same
file (or loading a sample twice) never re-runs the OCC pipeline.

Layout on disk:  <cache_dir>/<part_id>/{part.step, mesh.stl, analysis.json, meta.json}
In memory:       small LRU of PartAnalysis objects.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..geometry import VIEW_DEFS
from ..geometry.models import PartAnalysis, SectionProjection
from ..geometry.section_plane import auto_depth, cut_axis
from ..geometry.orientation import Orientation, OrientationRequest, resolve
from . import worker

MAX_SECTIONS_IN_MEMORY = 32
SECTION_VERSION = 1  # bump when section geometry changes, to skip stale disk caches

# Bump whenever PartAnalysis gains fields so stale disk caches are recomputed.
ANALYSIS_VERSION = 5


@dataclass
class PartEntry:
    part_id: str
    name: str
    source: str  # "sample" | "upload"
    sample_id: Optional[str]
    analysis: PartAnalysis
    directory: Path

    @property
    def orientation(self) -> Orientation:
        return Orientation(**self.analysis.orientation) if self.analysis.orientation else Orientation()

    @property
    def mesh_path(self) -> Path:
        return self.directory / "mesh.stl"


class PartStore:
    def __init__(self, root: Path, max_items: int = 24) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_items = max_items
        self._mem: OrderedDict[str, PartEntry] = OrderedDict()
        self._mem_lock = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._sections: OrderedDict[tuple, SectionProjection] = OrderedDict()

    @staticmethod
    def make_id(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()[:16]

    def _lock_for(self, part_id: str) -> threading.Lock:
        with self._mem_lock:
            return self._locks.setdefault(part_id, threading.Lock())

    def _remember(self, entry: PartEntry) -> PartEntry:
        with self._mem_lock:
            self._mem[entry.part_id] = entry
            self._mem.move_to_end(entry.part_id)
            while len(self._mem) > self.max_items:
                self._mem.popitem(last=False)
        return entry

    def section(self, entry: PartEntry, view: str, depth: Optional[float]) -> SectionProjection:
        """Full section of `view`, cached in memory and next to the analysis on disk.
        depth None = auto (through the most hole axes)."""
        g = entry.analysis.geometry
        vd = VIEW_DEFS[view]
        i, _ = cut_axis(vd)
        if depth is None:
            depth = auto_depth(g, vd)
        depth = round(min(max(depth, 0.0), g.size[i]), 3)
        key = (entry.part_id, view, depth)
        with self._mem_lock:
            if key in self._sections:
                self._sections.move_to_end(key)
                return self._sections[key]
        path = entry.directory / f"section_v{SECTION_VERSION}_{view}_{depth:.3f}.json"
        with self._lock_for(entry.part_id):
            sec = None
            if path.is_file():
                try:
                    sec = SectionProjection.model_validate_json(path.read_text(encoding="utf-8"))
                except Exception:
                    sec = None
            if sec is None:
                sec = worker.run(worker.section_job, entry.directory / "part.step", entry.analysis, view,
                                 depth, entry.orientation)
                path.write_text(sec.model_dump_json(), encoding="utf-8")
        with self._mem_lock:
            self._sections[key] = sec
            while len(self._sections) > MAX_SECTIONS_IN_MEMORY:
                self._sections.popitem(last=False)
        return sec

    def step_bytes(self, entry: PartEntry) -> bytes:
        return (entry.directory / "part.step").read_bytes()

    def get(self, part_id: str) -> Optional[PartEntry]:
        if not part_id.isalnum():
            return None
        with self._mem_lock:
            entry = self._mem.get(part_id)
            if entry is not None:
                self._mem.move_to_end(part_id)
                return entry
        return self._load_from_disk(part_id)

    def _load_from_disk(self, part_id: str) -> Optional[PartEntry]:
        d = self.root / part_id
        analysis_file, meta_file = d / "analysis.json", d / "meta.json"
        if not (analysis_file.is_file() and meta_file.is_file()):
            return None
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if meta.get("version") != ANALYSIS_VERSION:
                return None
            analysis = PartAnalysis.model_validate_json(analysis_file.read_text(encoding="utf-8"))
        except Exception:
            return None  # stale / corrupt cache -> recompute on next ingest
        return self._remember(PartEntry(part_id, meta["name"], meta["source"],
                                        meta.get("sample_id"), analysis, d))

    def ingest(
        self,
        data: bytes,
        name: str,
        source: str,
        sample_id: Optional[str] = None,
        max_faces: Optional[int] = None,
        max_solids: Optional[int] = None,
        orientation: Optional[OrientationRequest] = None,
    ) -> PartEntry:
        # Same file in another orientation = another drawing: the orientation key is
        # part of the id, so every endpoint (layout / annotate / export) just works.
        orient = resolve(orientation or OrientationRequest(), data)
        part_id = f"{self.make_id(data)}{orient.key}"
        with self._lock_for(part_id):
            entry = self.get(part_id)
            if entry is not None:
                return entry
            d = self.root / part_id
            d.mkdir(parents=True, exist_ok=True)
            step = d / "part.step"
            step.write_bytes(data)
            try:
                # OpenCascade runs in the CAD worker process so this server stays responsive
                analysis = worker.run(worker.analyze_job, step, d / "mesh.stl", max_faces, max_solids, orient)
            except Exception:
                shutil.rmtree(d, ignore_errors=True)  # don't leave rejected uploads on disk
                raise
            analysis.part_name = name
            analysis.orientation = orient.model_dump()
            (d / "analysis.json").write_text(analysis.model_dump_json(), encoding="utf-8")
            (d / "meta.json").write_text(
                json.dumps({"name": name, "source": source, "sample_id": sample_id,
                            "version": ANALYSIS_VERSION}), encoding="utf-8"
            )
            return self._remember(PartEntry(part_id, name, source, sample_id, analysis, d))

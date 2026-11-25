"""Content-addressed cache of analysed parts.

part_id = first 16 hex chars of sha256(step bytes), so re-uploading the same
file (or loading a sample twice) never re-runs the OCC pipeline.

Layout on disk:  <cache_dir>/<part_id>/{part.step, mesh.stl, analysis.json, meta.json}
In memory:       small LRU of PartAnalysis objects.
"""
from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..geometry.models import PartAnalysis
from ..pipeline import analyze_part


@dataclass
class PartEntry:
    part_id: str
    name: str
    source: str  # "sample" | "upload"
    sample_id: Optional[str]
    analysis: PartAnalysis
    directory: Path

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
            analysis = PartAnalysis.model_validate_json(analysis_file.read_text(encoding="utf-8"))
        except Exception:
            return None  # stale / corrupt cache -> recompute on next ingest
        return self._remember(PartEntry(part_id, meta["name"], meta["source"],
                                        meta.get("sample_id"), analysis, d))

    def ingest(self, data: bytes, name: str, source: str, sample_id: Optional[str] = None) -> PartEntry:
        part_id = self.make_id(data)
        with self._lock_for(part_id):
            entry = self.get(part_id)
            if entry is not None:
                return entry
            d = self.root / part_id
            d.mkdir(parents=True, exist_ok=True)
            step = d / "part.step"
            step.write_bytes(data)
            analysis = analyze_part(step, mesh_out=d / "mesh.stl")
            analysis.part_name = name
            (d / "analysis.json").write_text(analysis.model_dump_json(), encoding="utf-8")
            (d / "meta.json").write_text(
                json.dumps({"name": name, "source": source, "sample_id": sample_id}), encoding="utf-8"
            )
            return self._remember(PartEntry(part_id, name, source, sample_id, analysis, d))

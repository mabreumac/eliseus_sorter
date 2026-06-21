"""Benchmark timing and aggregate run metrics."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SortRuntime:
    scan_seconds: float = 0.0
    cluster_seconds: float = 0.0
    copy_seconds: float = 0.0
    num_images: int = 0
    num_faces_detected: int = 0
    num_images_with_face: int = 0
    num_images_no_face: int = 0

    @property
    def total_seconds(self) -> float:
        return self.scan_seconds + self.cluster_seconds + self.copy_seconds


@dataclass
class BenchmarkRuntime:
    sort: SortRuntime = field(default_factory=SortRuntime)
    score_seconds: float = 0.0
    viz_seconds: float = 0.0

    @property
    def total_seconds(self) -> float:
        return self.sort.total_seconds + self.score_seconds + self.viz_seconds

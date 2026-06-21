"""Benchmark timing and aggregate run metrics."""

from __future__ import annotations

from dataclasses import dataclass, field

from sort_runtime import SortRuntime

__all__ = ["SortRuntime", "BenchmarkRuntime"]


@dataclass
class BenchmarkRuntime:
    sort: SortRuntime = field(default_factory=SortRuntime)
    score_seconds: float = 0.0
    viz_seconds: float = 0.0

    @property
    def total_seconds(self) -> float:
        return self.sort.total_seconds + self.score_seconds + self.viz_seconds

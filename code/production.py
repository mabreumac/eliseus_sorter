"""Production sort: input folder → class/person folders."""

from __future__ import annotations

from cluster_sort import (
    BatchSortResult,
    SortConfig,
    SortResult,
    run_batch_sort,
    run_cluster_sort,
)

__all__ = [
    "BatchSortResult",
    "SortConfig",
    "SortResult",
    "run_sort",
]


def run_sort(*args, **kwargs) -> SortResult:
    return run_batch_sort(*args, **kwargs)

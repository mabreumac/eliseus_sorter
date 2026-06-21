"""Production sort: input folder → clustered person folders."""

from __future__ import annotations

from cluster_sort import SortConfig, SortResult, run_cluster_sort

__all__ = ["SortConfig", "SortResult", "run_sort"]


def run_sort(*args, **kwargs) -> SortResult:
    return run_cluster_sort(*args, **kwargs)

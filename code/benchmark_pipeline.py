"""Benchmarking: cluster-sort test photos and score against ground-truth filenames."""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app_paths import benchmark_data_dir, results_dir
from benchmark_eval import (
    infer_cluster_mapping,
    print_benchmark_score,
    save_benchmark_score,
    score_cluster_sort,
)
from benchmark_metrics import BenchmarkRuntime
from benchmark_viz import generate_benchmark_visualizations
from cluster_sort import SortConfig, SortResult, run_cluster_sort
from config import GROUP_OUTPUT_FOLDER, MATCH_TOLERANCE
from group_photos import GroupPhotoSettings
from image_utils import count_test_subset_images

ProgressCallback = Callable[[str, int, int, str], None]
CancelCallback = Callable[[], bool]

BENCHMARK_GROUND_TRUTH = benchmark_data_dir() / "ground_truth"
BENCHMARK_TEST_SUBSET = benchmark_data_dir() / "test_subset"
BENCHMARK_OUTPUT = benchmark_data_dir() / "output"
BENCHMARK_REPORTS = results_dir()


@dataclass(frozen=True)
class BenchmarkConfig:
    ground_truth_dir: Path = BENCHMARK_GROUND_TRUTH
    test_subset_dir: Path = BENCHMARK_TEST_SUBSET
    output_dir: Path = BENCHMARK_OUTPUT
    reports_dir: Path = BENCHMARK_REPORTS
    tolerance: float = MATCH_TOLERANCE
    group_settings: GroupPhotoSettings = field(default_factory=GroupPhotoSettings)


def ensure_benchmark_dirs(config: BenchmarkConfig) -> None:
    config.ground_truth_dir.mkdir(parents=True, exist_ok=True)
    config.test_subset_dir.mkdir(parents=True, exist_ok=True)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.reports_dir.mkdir(parents=True, exist_ok=True)


def _prepare_output_dir(output_dir: Path) -> None:
    if not output_dir.is_dir():
        output_dir.mkdir(parents=True, exist_ok=True)
        return
    for child in output_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def run_benchmark_sort(
    config: BenchmarkConfig,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> SortResult:
    """Cluster-sort test_subset into output/ (same pipeline as production)."""
    ensure_benchmark_dirs(config)
    total = count_test_subset_images(config.test_subset_dir)
    if total == 0:
        raise ValueError(f"No images in {config.test_subset_dir}")

    _prepare_output_dir(config.output_dir)

    return run_cluster_sort(
        SortConfig(
            input_dir=config.test_subset_dir,
            output_dir=config.output_dir,
            tolerance=config.tolerance,
            group_settings=config.group_settings,
        ),
        on_progress=on_progress,
        should_cancel=should_cancel,
    )


def run_benchmark_score(
    sort_result: SortResult,
    config: BenchmarkConfig,
    runtime: BenchmarkRuntime | None = None,
) -> Path | None:
    """Compare cluster output to ground truth using original filenames."""
    if not config.ground_truth_dir.is_dir():
        print(f"Ground truth not found: {config.ground_truth_dir}")
        return None

    from image_utils import ground_truth_labels

    bench_runtime = runtime or BenchmarkRuntime()
    if runtime is None and sort_result.runtime.num_images:
        bench_runtime.sort = sort_result.runtime

    labels = ground_truth_labels(config.ground_truth_dir)
    group_folder = config.group_settings.resolved_group_output_folder() or GROUP_OUTPUT_FOLDER

    t0 = time.perf_counter()
    score = score_cluster_sort(
        sort_result.results,
        labels,
        config.output_dir,
        group_folder=group_folder,
    )
    mapping = infer_cluster_mapping(
        sort_result.results, labels, group_folder=group_folder
    )
    bench_runtime.score_seconds = time.perf_counter() - t0

    print_benchmark_score(score, mapping)
    json_path, mapping_csv, profile_csv, files_csv = save_benchmark_score(
        score, config.reports_dir, mapping, labels
    )
    print(
        f"Score reports:\n  {json_path}\n  {mapping_csv}\n  {profile_csv}\n  {files_csv}"
    )

    dashboard = generate_benchmark_visualizations(
        score,
        labels,
        mapping,
        bench_runtime,
        config.reports_dir,
        tolerance=config.tolerance,
        num_clusters=sort_result.num_clusters,
    )
    print(f"\nVisualizations:\n  {dashboard}\n  {dashboard.parent}/\n")
    return dashboard

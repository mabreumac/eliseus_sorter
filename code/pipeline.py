"""Shared pipeline orchestration for CLI and GUI runners."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from build_reference import BuildReferenceStats, build_reference_database
from config import (
    DATABASE_PATH,
    GROUND_TRUTH_DIR,
    MATCH_TOLERANCE,
    OUTPUT_DIR,
    TEST_SUBSET_DIR,
)
from database import count_reference_faces, count_students, init_database
from image_utils import count_ground_truth_images, count_test_subset_images
from match_subset import MatchResult, match_test_subset
from reporting import results_to_dataframe, save_reports

ProgressCallback = Callable[[str, int, int, str], None]
CancelCallback = Callable[[], bool]


@dataclass(frozen=True)
class PipelineConfig:
    """Runtime paths and settings (overrides defaults from config.py)."""

    ground_truth_dir: Path = GROUND_TRUTH_DIR
    test_subset_dir: Path = TEST_SUBSET_DIR
    database_path: Path = DATABASE_PATH
    output_dir: Path = OUTPUT_DIR
    tolerance: float = MATCH_TOLERANCE


@dataclass
class MatchRunResult:
    """Outcome of a full match pass."""

    results: list[MatchResult]
    json_path: Optional[Path] = None
    csv_path: Optional[Path] = None
    dataframe: Optional[object] = None  # pandas DataFrame; typed loosely for optional import


def ensure_directories(config: PipelineConfig) -> None:
    config.ground_truth_dir.mkdir(parents=True, exist_ok=True)
    config.test_subset_dir.mkdir(parents=True, exist_ok=True)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.database_path.parent.mkdir(parents=True, exist_ok=True)


def run_build_phase(
    config: PipelineConfig,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> BuildReferenceStats:
    """Phase 1: index ground-truth embeddings."""
    ensure_directories(config)
    total = count_ground_truth_images(config.ground_truth_dir)
    if on_progress:
        on_progress("build", 0, max(total, 1), "Starting reference build…")

    return build_reference_database(
        ground_truth_dir=config.ground_truth_dir,
        db_path=config.database_path,
        on_progress=on_progress,
        should_cancel=should_cancel,
        total_images=total,
    )


def run_match_phase(
    config: PipelineConfig,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> MatchRunResult:
    """Phase 2+3: match test subset and write reports."""
    ensure_directories(config)
    init_database(config.database_path)

    ref_count = count_reference_faces(config.database_path)
    if ref_count == 0:
        raise ValueError(
            "Reference database is empty. Build the reference index first."
        )

    total = count_test_subset_images(config.test_subset_dir)
    if on_progress:
        on_progress("match", 0, max(total, 1), "Starting photo matching…")

    results = match_test_subset(
        test_subset_dir=config.test_subset_dir,
        db_path=config.database_path,
        tolerance=config.tolerance,
        on_progress=on_progress,
        should_cancel=should_cancel,
        total_images=total,
    )

    if not results:
        return MatchRunResult(results=[])

    json_path, csv_path = save_reports(
        results,
        output_dir=config.output_dir,
        tolerance=config.tolerance,
    )
    df = results_to_dataframe(results)
    return MatchRunResult(
        results=results,
        json_path=json_path,
        csv_path=csv_path,
        dataframe=df,
    )


def run_full_pipeline(
    config: PipelineConfig,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> tuple[BuildReferenceStats, MatchRunResult]:
    """Run build then match."""
    stats = run_build_phase(config, on_progress, should_cancel)
    if should_cancel and should_cancel():
        return stats, MatchRunResult(results=[])
    match_result = run_match_phase(config, on_progress, should_cancel)
    return stats, match_result

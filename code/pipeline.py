"""Shared pipeline orchestration for CLI and GUI runners."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app_paths import ensure_data_dirs
from build_reference import BuildReferenceStats, build_reference_database
from config import (
    DATABASE_PATH,
    GROUND_TRUTH_DIR,
    MATCH_TOLERANCE,
    OUTPUT_DIR,
    SORTED_STUDENTS_DIR,
    TEST_SUBSET_DIR,
)
from database import count_reference_faces, count_students, init_database
from group_photos import GroupPhotoSettings
from image_utils import count_ground_truth_images, count_match_sources
from match_subset import MatchResult, match_test_subset
from reporting import results_to_dataframe, save_reports
from student_sorting import apply_student_folder_sorting

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
    group_settings: GroupPhotoSettings = field(default_factory=GroupPhotoSettings)


@dataclass
class MatchRunResult:
    """Outcome of a full match pass."""

    results: list[MatchResult]
    json_path: Optional[Path] = None
    csv_path: Optional[Path] = None
    dataframe: Optional[object] = None
    sorted_output_dir: Optional[Path] = None


def ensure_directories(config: PipelineConfig) -> None:
    ensure_data_dirs()
    config.ground_truth_dir.mkdir(parents=True, exist_ok=True)
    config.test_subset_dir.mkdir(parents=True, exist_ok=True)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.database_path.parent.mkdir(parents=True, exist_ok=True)
    group_dir = config.group_settings.resolved_group_photos_dir()
    if group_dir is not None:
        group_dir.mkdir(parents=True, exist_ok=True)
    if config.group_settings.sort_to_student_folders:
        config.group_settings.sorted_output_dir.mkdir(parents=True, exist_ok=True)


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
        group_settings=config.group_settings,
        on_progress=on_progress,
        should_cancel=should_cancel,
        total_images=total,
    )


def run_match_phase(
    config: PipelineConfig,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> MatchRunResult:
    """Phase 2+3: match photos, optionally sort group matches, write reports."""
    ensure_directories(config)
    init_database(config.database_path)

    ref_count = count_reference_faces(config.database_path)
    if ref_count == 0:
        raise ValueError(
            "Reference database is empty. Build the reference index first."
        )

    group_dir = config.group_settings.resolved_group_photos_dir()
    total = count_match_sources(config.test_subset_dir, group_dir)
    if total == 0:
        raise ValueError(
            "No images found. Add photos to the test subset and/or group photos folder."
        )

    if on_progress:
        on_progress("match", 0, max(total, 1), "Starting photo matching…")

    results = match_test_subset(
        test_subset_dir=config.test_subset_dir,
        db_path=config.database_path,
        tolerance=config.tolerance,
        group_settings=config.group_settings,
        group_photos_dir=group_dir,
        on_progress=on_progress,
        should_cancel=should_cancel,
        total_images=total,
    )

    if not results:
        return MatchRunResult(results=[])

    sorted_dir: Optional[Path] = None
    if config.group_settings.sort_to_student_folders:
        sorted_dir = config.group_settings.sorted_output_dir
        results = apply_student_folder_sorting(results, sorted_dir)

    json_path, csv_path = save_reports(
        results,
        output_dir=config.output_dir,
        tolerance=config.tolerance,
        group_settings=config.group_settings,
    )
    df = results_to_dataframe(results)
    return MatchRunResult(
        results=results,
        json_path=json_path,
        csv_path=csv_path,
        dataframe=df,
        sorted_output_dir=sorted_dir,
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

"""Copy matched photos into per-student output folders (production)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from config import UNMATCHED_FOLDER
from match_subset import MatchResult, is_known_match

logger = logging.getLogger(__name__)


def _unique_destination(directory: Path, filename: str) -> Path:
    dest = directory / filename
    if not dest.exists():
        return dest
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 2
    while True:
        candidate = directory / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def copy_match_to_student_folder(
    source_path: Path,
    folder_name: str,
    output_root: Path,
    face_index: Optional[int] = None,
) -> Path:
    dest_dir = output_root / folder_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    if face_index is not None and face_index > 0:
        filename = f"{source_path.stem}_face{face_index + 1}{source_path.suffix}"
    else:
        filename = source_path.name

    dest_path = _unique_destination(dest_dir, filename)
    import shutil

    shutil.copy2(source_path, dest_path)
    logger.info("Copied %s -> %s", source_path.name, dest_path)
    return dest_path


def apply_production_sorting(
    results: list[MatchResult],
    output_root: Path,
) -> list[MatchResult]:
    """Copy every match into output_root/<student>/ or output_root/_unmatched/."""
    output_root.mkdir(parents=True, exist_ok=True)
    updated: list[MatchResult] = []

    for result in results:
        folder = (
            result.matched_student
            if is_known_match(result.matched_student)
            else UNMATCHED_FOLDER
        )
        dest = copy_match_to_student_folder(
            Path(result.test_path),
            folder,
            output_root,
            face_index=result.face_index,
        )
        updated.append(
            MatchResult(
                test_file=result.test_file,
                test_path=result.test_path,
                matched_student=result.matched_student,
                distance=result.distance,
                num_faces=result.num_faces,
                reference_file=result.reference_file,
                error=result.error,
                face_index=result.face_index,
                source_kind=result.source_kind,
                is_group_photo=result.is_group_photo,
                sorted_copy_path=str(dest),
            )
        )

    return updated


# Benchmark-only helper (group photos folder workflow)
def apply_student_folder_sorting(
    results: list[MatchResult],
    sorted_root: Path,
) -> list[MatchResult]:
    """Copy group-photo matches only (benchmark reports)."""
    sorted_root.mkdir(parents=True, exist_ok=True)
    updated: list[MatchResult] = []

    for result in results:
        is_group = result.source_kind == "group_photos" or result.num_faces > 1
        if not is_known_match(result.matched_student) or not is_group:
            updated.append(result)
            continue
        dest = copy_match_to_student_folder(
            Path(result.test_path),
            result.matched_student,
            sorted_root,
            face_index=result.face_index,
        )
        updated.append(
            MatchResult(
                test_file=result.test_file,
                test_path=result.test_path,
                matched_student=result.matched_student,
                distance=result.distance,
                num_faces=result.num_faces,
                reference_file=result.reference_file,
                error=result.error,
                face_index=result.face_index,
                source_kind=result.source_kind,
                is_group_photo=result.is_group_photo,
                sorted_copy_path=str(dest),
            )
        )

    return updated

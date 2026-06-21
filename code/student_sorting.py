"""Copy matched photos into per-student folders (originals are never moved)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

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
    student_name: str,
    sorted_root: Path,
    face_index: Optional[int] = None,
) -> Path:
    """Copy a photo into sorted_root/<student_name>/; returns destination path."""
    dest_dir = sorted_root / student_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    if face_index is not None and face_index > 0:
        filename = f"{source_path.stem}_face{face_index + 1}{source_path.suffix}"
    else:
        filename = source_path.name

    dest_path = _unique_destination(dest_dir, filename)
    shutil.copy2(source_path, dest_path)
    logger.info("Copied %s -> %s", source_path.name, dest_path)
    return dest_path


def should_sort_result(result: MatchResult) -> bool:
    """Whether this match should be copied into a student folder."""
    return result.source_kind == "group_photos" or result.num_faces > 1


def apply_student_folder_sorting(
    results: list[MatchResult],
    sorted_root: Path,
) -> list[MatchResult]:
    """Copy eligible matches into student subfolders."""
    sorted_root.mkdir(parents=True, exist_ok=True)
    updated: list[MatchResult] = []

    for result in results:
        if not is_known_match(result.matched_student) or not should_sort_result(result):
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

"""Move or copy matched photos into per-student output folders (production)."""

from __future__ import annotations

import logging
import shutil
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


def _destination_filename(source_path: Path, face_index: Optional[int]) -> str:
    if face_index is not None and face_index > 0:
        return f"{source_path.stem}_face{face_index + 1}{source_path.suffix}"
    return source_path.name


def transfer_match_to_student_folder(
    source_path: Path,
    folder_name: str,
    output_root: Path,
    *,
    face_index: Optional[int] = None,
    move: bool = False,
) -> Path:
    dest_dir = output_root / folder_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = _destination_filename(source_path, face_index)
    dest_path = _unique_destination(dest_dir, filename)

    if move:
        shutil.move(str(source_path), dest_path)
        logger.info("Moved %s -> %s", source_path.name, dest_path)
    else:
        shutil.copy2(source_path, dest_path)
        logger.info("Copied %s -> %s", source_path.name, dest_path)
    return dest_path


def copy_match_to_student_folder(
    source_path: Path,
    folder_name: str,
    output_root: Path,
    face_index: Optional[int] = None,
) -> Path:
    return transfer_match_to_student_folder(
        source_path,
        folder_name,
        output_root,
        face_index=face_index,
        move=False,
    )


def apply_production_sorting(
    results: list[MatchResult],
    output_root: Path,
    *,
    in_place: bool = False,
) -> list[MatchResult]:
    """Place every match into output_root/<student>/ or output_root/_unmatched/.

    When in_place is True, the first destination for each source file is moved;
    additional destinations (e.g. group photo into several person folders) are copied.
    """
    output_root.mkdir(parents=True, exist_ok=True)
    updated: list[MatchResult] = []
    current_location: dict[str, Path] = {}

    for result in results:
        folder = (
            result.matched_student
            if is_known_match(result.matched_student)
            else UNMATCHED_FOLDER
        )
        dest_root = (
            output_root / result.class_folder if result.class_folder else output_root
        )
        original_key = str(Path(result.test_path).resolve())
        if original_key in current_location:
            source = current_location[original_key]
            move = False
        else:
            source = Path(result.test_path)
            move = in_place

        dest = transfer_match_to_student_folder(
            source,
            folder,
            dest_root,
            face_index=result.face_index,
            move=move,
        )
        if move:
            current_location[original_key] = dest
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
                class_folder=result.class_folder,
                is_class_photo=result.is_class_photo,
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

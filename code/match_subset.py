"""Phase 2: Match unassigned test photos against reference embeddings."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generator, Optional

import numpy as np

from config import DATABASE_PATH, MATCH_TOLERANCE, TEST_SUBSET_DIR
from database import iter_reference_embeddings
from embeddings import encode_faces_from_path, euclidean_distance
from group_photos import GroupPhotoMode, GroupPhotoSettings
from image_utils import iter_match_sources

logger = logging.getLogger(__name__)

UNKNOWN_LABEL = "Unknown"
NO_FACE_LABEL = "No Face Detected"
SKIPPED_GROUP_LABEL = "Skipped (Group Photo)"

KNOWN_MATCH_LABELS = frozenset({UNKNOWN_LABEL, NO_FACE_LABEL, SKIPPED_GROUP_LABEL})


def is_known_match(student_name: str) -> bool:
    return student_name not in KNOWN_MATCH_LABELS


ProgressCallback = Callable[[str, int, int, str], None]
CancelCallback = Callable[[], bool]


@dataclass(frozen=True)
class MatchResult:
    """Single face match outcome (one row per detected face when applicable)."""

    test_file: str
    test_path: str
    matched_student: str
    distance: Optional[float]
    num_faces: int
    reference_file: Optional[str] = None
    error: Optional[str] = None
    face_index: Optional[int] = None
    source_kind: str = "test_subset"
    is_group_photo: bool = False
    sorted_copy_path: Optional[str] = None


def _best_reference_match(
    query_embedding: np.ndarray,
    tolerance: float,
    db_path: Path,
) -> tuple[Optional[str], Optional[float], Optional[str]]:
    best_student: Optional[str] = None
    best_distance = float("inf")
    best_reference_file: Optional[str] = None

    for student_name, ref_path, ref_embedding in iter_reference_embeddings(db_path):
        distance = euclidean_distance(query_embedding, ref_embedding)
        if distance < best_distance:
            best_distance = distance
            best_student = student_name
            best_reference_file = ref_path

    if best_student is None or best_distance > tolerance:
        return None, best_distance if best_distance != float("inf") else None, None

    return best_student, best_distance, best_reference_file


def match_image_faces(
    image_path: Path,
    tolerance: float = MATCH_TOLERANCE,
    db_path: Path = DATABASE_PATH,
    group_settings: Optional[GroupPhotoSettings] = None,
    source_kind: str = "test_subset",
) -> list[MatchResult]:
    """Encode and match one image; may return multiple rows for group photos."""
    settings = group_settings or GroupPhotoSettings()
    encoding = encode_faces_from_path(image_path, settings.mode)
    resolved = str(image_path.resolve())
    is_group = encoding.num_faces > 1

    if encoding.error:
        return [
            MatchResult(
                test_file=image_path.name,
                test_path=resolved,
                matched_student=UNKNOWN_LABEL,
                distance=None,
                num_faces=encoding.num_faces,
                error=encoding.error,
                source_kind=source_kind,
                is_group_photo=is_group,
            )
        ]

    if encoding.skipped_group:
        return [
            MatchResult(
                test_file=image_path.name,
                test_path=resolved,
                matched_student=SKIPPED_GROUP_LABEL,
                distance=None,
                num_faces=encoding.num_faces,
                source_kind=source_kind,
                is_group_photo=True,
            )
        ]

    if not encoding.faces:
        label = NO_FACE_LABEL if encoding.num_faces == 0 else UNKNOWN_LABEL
        return [
            MatchResult(
                test_file=image_path.name,
                test_path=resolved,
                matched_student=label,
                distance=None,
                num_faces=encoding.num_faces,
                source_kind=source_kind,
                is_group_photo=is_group,
            )
        ]

    results: list[MatchResult] = []
    for face in encoding.faces:
        student, distance, ref_file = _best_reference_match(
            face.embedding, tolerance, db_path
        )
        matched = student if student is not None else UNKNOWN_LABEL
        results.append(
            MatchResult(
                test_file=image_path.name,
                test_path=resolved,
                matched_student=matched,
                distance=distance,
                num_faces=encoding.num_faces,
                reference_file=ref_file,
                face_index=face.face_index,
                source_kind=source_kind,
                is_group_photo=is_group,
            )
        )
    return results


def match_test_image(
    image_path: Path,
    tolerance: float = MATCH_TOLERANCE,
    db_path: Path = DATABASE_PATH,
    group_settings: Optional[GroupPhotoSettings] = None,
    source_kind: str = "test_subset",
) -> MatchResult:
    """Match one image; returns the first result row for backward compatibility."""
    results = match_image_faces(
        image_path,
        tolerance=tolerance,
        db_path=db_path,
        group_settings=group_settings,
        source_kind=source_kind,
    )
    return results[0]


def iter_test_matches(
    test_subset_dir: Path = TEST_SUBSET_DIR,
    tolerance: float = MATCH_TOLERANCE,
    db_path: Path = DATABASE_PATH,
    group_settings: Optional[GroupPhotoSettings] = None,
    group_photos_dir: Path | None = None,
) -> Generator[MatchResult, None, None]:
    """Stream match results for test subset and optional group photos."""
    for source_kind, image_path in iter_match_sources(test_subset_dir, group_photos_dir):
        yield from match_image_faces(
            image_path,
            tolerance=tolerance,
            db_path=db_path,
            group_settings=group_settings,
            source_kind=source_kind,
        )


def match_test_subset(
    test_subset_dir: Path = TEST_SUBSET_DIR,
    tolerance: float = MATCH_TOLERANCE,
    db_path: Path = DATABASE_PATH,
    group_settings: Optional[GroupPhotoSettings] = None,
    group_photos_dir: Path | None = None,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
    total_images: Optional[int] = None,
) -> list[MatchResult]:
    """Match all configured sources with optional progress and cancellation."""
    settings = group_settings or GroupPhotoSettings()
    results: list[MatchResult] = []
    total = total_images if total_images is not None else 0
    current = 0

    for source_kind, image_path in iter_match_sources(test_subset_dir, group_photos_dir):
        if should_cancel and should_cancel():
            logger.info("Matching cancelled by user")
            break

        current += 1
        label = "group" if source_kind == "group_photos" else "test"
        if on_progress:
            on_progress(
                "match",
                current,
                max(total, current),
                f"Matching {label}: {image_path.name}",
            )

        results.extend(
            match_image_faces(
                image_path,
                tolerance=tolerance,
                db_path=db_path,
                group_settings=settings,
                source_kind=source_kind,
            )
        )

    return results

"""Phase 2: Match unassigned test photos against reference embeddings."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generator, Optional

import numpy as np

from config import DATABASE_PATH, MATCH_TOLERANCE, TEST_SUBSET_DIR
from database import iter_reference_embeddings
from embeddings import encode_face_from_path, euclidean_distance
from image_utils import iter_test_subset_images

logger = logging.getLogger(__name__)

UNKNOWN_LABEL = "Unknown"
NO_FACE_LABEL = "No Face Detected"

ProgressCallback = Callable[[str, int, int, str], None]
CancelCallback = Callable[[], bool]


@dataclass(frozen=True)
class MatchResult:
    """Single test-image classification outcome."""

    test_file: str
    test_path: str
    matched_student: str
    distance: Optional[float]
    num_faces: int
    reference_file: Optional[str] = None
    error: Optional[str] = None


def _best_reference_match(
    query_embedding: np.ndarray,
    tolerance: float,
    db_path: Path,
) -> tuple[Optional[str], Optional[float], Optional[str]]:
    """
    Compare query embedding against all references streamed from SQLite.

    Returns (student_name, distance, reference_file_path) or (None, None, None).
    """
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


def match_test_image(
    image_path: Path,
    tolerance: float = MATCH_TOLERANCE,
    db_path: Path = DATABASE_PATH,
) -> MatchResult:
    """Encode one test image and find the closest reference face."""
    result = encode_face_from_path(image_path)

    if result.error:
        return MatchResult(
            test_file=image_path.name,
            test_path=str(image_path.resolve()),
            matched_student=UNKNOWN_LABEL,
            distance=None,
            num_faces=result.num_faces,
            error=result.error,
        )

    if result.embedding is None:
        label = NO_FACE_LABEL if result.num_faces == 0 else UNKNOWN_LABEL
        return MatchResult(
            test_file=image_path.name,
            test_path=str(image_path.resolve()),
            matched_student=label,
            distance=None,
            num_faces=result.num_faces,
        )

    student, distance, ref_file = _best_reference_match(
        result.embedding, tolerance, db_path
    )
    matched = student if student is not None else UNKNOWN_LABEL

    return MatchResult(
        test_file=image_path.name,
        test_path=str(image_path.resolve()),
        matched_student=matched,
        distance=distance,
        num_faces=result.num_faces,
        reference_file=ref_file,
    )


def iter_test_matches(
    test_subset_dir: Path = TEST_SUBSET_DIR,
    tolerance: float = MATCH_TOLERANCE,
    db_path: Path = DATABASE_PATH,
) -> Generator[MatchResult, None, None]:
    """Stream match results for each image in the test subset."""
    for image_path in iter_test_subset_images(test_subset_dir):
        yield match_test_image(image_path, tolerance=tolerance, db_path=db_path)


def match_test_subset(
    test_subset_dir: Path = TEST_SUBSET_DIR,
    tolerance: float = MATCH_TOLERANCE,
    db_path: Path = DATABASE_PATH,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
    total_images: Optional[int] = None,
) -> list[MatchResult]:
    """Match all test images with optional progress and cancellation."""
    results: list[MatchResult] = []
    total = total_images if total_images is not None else 0
    current = 0

    for image_path in iter_test_subset_images(test_subset_dir):
        if should_cancel and should_cancel():
            logger.info("Matching cancelled by user")
            break

        current += 1
        if on_progress:
            on_progress(
                "match",
                current,
                max(total, current),
                f"Matching {image_path.name}",
            )

        results.append(
            match_test_image(image_path, tolerance=tolerance, db_path=db_path)
        )

    return results

"""Phase 1: Build the reference embedding database from ground truth."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from config import GROUND_TRUTH_DIR, DATABASE_PATH
from database import file_path_exists, init_database, insert_reference_face
from embeddings import encode_face_from_path
from image_utils import iter_ground_truth_images

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int, str], None]
CancelCallback = Callable[[], bool]


@dataclass
class BuildReferenceStats:
    """Summary counters for the reference build pass."""

    processed: int = 0
    inserted: int = 0
    skipped_existing: int = 0
    no_face: int = 0
    errors: int = 0
    cancelled: bool = False
    error_messages: list[str] = field(default_factory=list)


def build_reference_database(
    ground_truth_dir: Path = GROUND_TRUTH_DIR,
    db_path: Path = DATABASE_PATH,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
    total_images: Optional[int] = None,
) -> BuildReferenceStats:
    """
    Index ground-truth photos into SQLite.

    Skips file paths already present in the database (checkpoint-safe).
    """
    init_database(db_path)
    stats = BuildReferenceStats()
    total = total_images if total_images is not None else 0

    for student_name, image_path in iter_ground_truth_images(ground_truth_dir):
        if should_cancel and should_cancel():
            stats.cancelled = True
            logger.info("Reference build cancelled by user")
            break

        stats.processed += 1
        file_path = str(image_path.resolve())
        message = f"Indexing {student_name} / {image_path.name}"

        if on_progress:
            on_progress("build", stats.processed, max(total, stats.processed), message)

        if file_path_exists(file_path, db_path=db_path):
            stats.skipped_existing += 1
            logger.debug("Skipping existing: %s", file_path)
            continue

        result = encode_face_from_path(image_path)

        if result.error:
            stats.errors += 1
            msg = f"{image_path.name}: {result.error}"
            stats.error_messages.append(msg)
            logger.warning("Encoding error for %s — %s", image_path, result.error)
            continue

        if result.embedding is None:
            stats.no_face += 1
            logger.info("No face detected in %s", image_path)
            continue

        insert_reference_face(student_name, file_path, result.embedding, db_path=db_path)
        stats.inserted += 1
        logger.info("Indexed %s -> %s", student_name, image_path.name)

    return stats

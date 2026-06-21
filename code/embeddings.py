"""Face detection and encoding helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import face_recognition
import numpy as np

from image_utils import load_image_resized


@dataclass(frozen=True)
class EncodingResult:
    """Outcome of attempting to encode a face from one image."""

    embedding: Optional[np.ndarray]
    num_faces: int
    error: Optional[str] = None


def encode_face_from_path(image_path: Path) -> EncodingResult:
    """
    Detect faces and return a single 128-d embedding.

    Uses the first detected face when multiple faces are present.
    Returns embedding=None when no face is found or on recoverable errors.
    """
    try:
        image = load_image_resized(image_path)
    except (OSError, ValueError) as exc:
        return EncodingResult(embedding=None, num_faces=0, error=str(exc))

    try:
        locations = face_recognition.face_locations(image)
    except Exception as exc:  # noqa: BLE001 — dlib can raise varied errors
        return EncodingResult(embedding=None, num_faces=0, error=str(exc))

    if not locations:
        return EncodingResult(embedding=None, num_faces=0)

    try:
        encodings = face_recognition.face_encodings(image, known_face_locations=locations)
    except Exception as exc:  # noqa: BLE001
        return EncodingResult(embedding=None, num_faces=len(locations), error=str(exc))

    if not encodings:
        return EncodingResult(embedding=None, num_faces=len(locations))

    return EncodingResult(
        embedding=np.asarray(encodings[0], dtype=np.float64),
        num_faces=len(locations),
    )


def euclidean_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Euclidean distance between two face embeddings."""
    return float(np.linalg.norm(a - b))

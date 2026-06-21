"""Face detection and encoding helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import face_recognition
import numpy as np

from group_photos import GroupPhotoMode
from image_utils import load_image_resized


@dataclass(frozen=True)
class EncodingResult:
    """Outcome of attempting to encode a face from one image."""

    embedding: Optional[np.ndarray]
    num_faces: int
    error: Optional[str] = None


@dataclass(frozen=True)
class FaceEncoding:
    """One encoded face from an image."""

    face_index: int
    embedding: np.ndarray


@dataclass(frozen=True)
class MultiFaceEncodingResult:
    """All face encodings selected by the group-photo mode."""

    faces: list[FaceEncoding] = field(default_factory=list)
    num_faces: int = 0
    skipped_group: bool = False
    error: Optional[str] = None


def _face_area(location: tuple[int, int, int, int]) -> int:
    top, right, bottom, left = location
    return max(0, bottom - top) * max(0, right - left)


def _select_face_indices(
    locations: list[tuple[int, int, int, int]],
    mode: GroupPhotoMode,
) -> list[int]:
    if not locations:
        return []
    if len(locations) == 1:
        return [0]
    if mode == GroupPhotoMode.SKIP:
        return []
    if mode == GroupPhotoMode.FIRST_FACE:
        return [0]
    if mode == GroupPhotoMode.LARGEST_FACE:
        areas = [_face_area(loc) for loc in locations]
        return [areas.index(max(areas))]
    if mode == GroupPhotoMode.ALL_FACES:
        return list(range(len(locations)))
    return [0]


def encode_faces_from_path(
    image_path: Path,
    mode: GroupPhotoMode = GroupPhotoMode.FIRST_FACE,
) -> MultiFaceEncodingResult:
    """Detect faces and return embeddings according to group-photo mode."""
    try:
        image = load_image_resized(image_path)
    except (OSError, ValueError) as exc:
        return MultiFaceEncodingResult(error=str(exc))

    try:
        locations = face_recognition.face_locations(image)
    except Exception as exc:  # noqa: BLE001
        return MultiFaceEncodingResult(error=str(exc))

    if not locations:
        return MultiFaceEncodingResult(num_faces=0)

    indices = _select_face_indices(locations, mode)
    if len(locations) > 1 and mode == GroupPhotoMode.SKIP:
        return MultiFaceEncodingResult(num_faces=len(locations), skipped_group=True)

    try:
        encodings = face_recognition.face_encodings(image, known_face_locations=locations)
    except Exception as exc:  # noqa: BLE001
        return MultiFaceEncodingResult(num_faces=len(locations), error=str(exc))

    if not encodings:
        return MultiFaceEncodingResult(num_faces=len(locations))

    faces: list[FaceEncoding] = []
    for index in indices:
        if index < len(encodings):
            faces.append(
                FaceEncoding(
                    face_index=index,
                    embedding=np.asarray(encodings[index], dtype=np.float64),
                )
            )

    return MultiFaceEncodingResult(faces=faces, num_faces=len(locations))


def encode_face_from_path(image_path: Path) -> EncodingResult:
    """Encode a single face using the legacy first-face behaviour."""
    result = encode_faces_from_path(image_path, GroupPhotoMode.FIRST_FACE)
    if result.error:
        return EncodingResult(embedding=None, num_faces=result.num_faces, error=result.error)
    if not result.faces:
        return EncodingResult(embedding=None, num_faces=result.num_faces)
    return EncodingResult(
        embedding=result.faces[0].embedding,
        num_faces=result.num_faces,
    )


def euclidean_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Euclidean distance between two face embeddings."""
    return float(np.linalg.norm(a - b))

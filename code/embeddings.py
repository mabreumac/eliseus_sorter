"""Face detection and encoding via InsightFace (RetinaFace + ArcFace)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from config import MIN_FACE_AREA_RATIO, MIN_FACE_DET_SCORE
from face_engine import get_face_analysis
from group_photos import GroupPhotoMode


@dataclass(frozen=True)
class EncodingResult:
    embedding: Optional[np.ndarray]
    num_faces: int
    error: Optional[str] = None


@dataclass(frozen=True)
class FaceEncoding:
    face_index: int
    embedding: np.ndarray


@dataclass(frozen=True)
class MultiFaceEncodingResult:
    faces: list[FaceEncoding] = field(default_factory=list)
    num_faces: int = 0
    skipped_group: bool = False
    error: Optional[str] = None


def _face_area(bbox: np.ndarray) -> float:
    x1, y1, x2, y2 = bbox[:4]
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _det_score(face: object) -> float:
    score = getattr(face, "det_score", None)
    if score is None:
        return 1.0
    return float(score)


def _filter_significant_faces(detected: list) -> list:
    """Keep main-subject faces; drop low-confidence and tiny background detections."""
    if not detected:
        return []

    max_area = max(_face_area(face.bbox) for face in detected)
    if max_area <= 0:
        return list(detected)

    kept: list = []
    for face in detected:
        if _det_score(face) < MIN_FACE_DET_SCORE:
            continue
        if MIN_FACE_AREA_RATIO > 0 and _face_area(face.bbox) / max_area < MIN_FACE_AREA_RATIO:
            continue
        kept.append(face)
    return kept


def _select_face_indices(num_faces: int, areas: list[float], mode: GroupPhotoMode) -> list[int]:
    if num_faces == 0:
        return []
    if num_faces == 1:
        return [0]
    if mode == GroupPhotoMode.SKIP:
        return []
    if mode == GroupPhotoMode.FIRST_FACE:
        return [0]
    if mode == GroupPhotoMode.LARGEST_FACE:
        return [int(np.argmax(areas))]
    if mode == GroupPhotoMode.ALL_FACES:
        return list(range(num_faces))
    return [0]


def normalize_embedding(embedding: np.ndarray) -> np.ndarray:
    vec = np.asarray(embedding, dtype=np.float64).flatten()
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm


def _normalize(embedding: np.ndarray) -> np.ndarray:
    return normalize_embedding(embedding)


def _load_bgr(image_path: Path) -> np.ndarray | None:
    image = cv2.imread(str(image_path))
    if image is None:
        return None
    return image


def encode_faces_from_path(
    image_path: Path,
    mode: GroupPhotoMode = GroupPhotoMode.FIRST_FACE,
) -> MultiFaceEncodingResult:
    """Detect faces and return L2-normalized ArcFace embeddings."""
    image = _load_bgr(image_path)
    if image is None:
        return MultiFaceEncodingResult(error=f"cannot read image: {image_path.name}")

    try:
        detected = get_face_analysis().get(image)
    except Exception as exc:  # noqa: BLE001
        return MultiFaceEncodingResult(error=str(exc))

    if not detected:
        return MultiFaceEncodingResult(num_faces=0)

    detected = _filter_significant_faces(detected)
    if not detected:
        return MultiFaceEncodingResult(num_faces=0)

    # Largest faces first — stable ordering for group-photo modes.
    detected = sorted(detected, key=lambda f: _face_area(f.bbox), reverse=True)
    areas = [_face_area(face.bbox) for face in detected]
    indices = _select_face_indices(len(detected), areas, mode)

    if len(detected) > 1 and mode == GroupPhotoMode.SKIP:
        return MultiFaceEncodingResult(num_faces=len(detected), skipped_group=True)

    faces: list[FaceEncoding] = []
    for out_index, src_index in enumerate(indices):
        face = detected[src_index]
        raw = getattr(face, "normed_embedding", None)
        if raw is None:
            raw = getattr(face, "embedding", None)
        if raw is None:
            continue
        faces.append(
            FaceEncoding(
                face_index=out_index,
                embedding=_normalize(np.asarray(raw)),
            )
        )

    return MultiFaceEncodingResult(faces=faces, num_faces=len(detected))


def encode_face_from_path(image_path: Path) -> EncodingResult:
    result = encode_faces_from_path(image_path, GroupPhotoMode.FIRST_FACE)
    if result.error:
        return EncodingResult(embedding=None, num_faces=result.num_faces, error=result.error)
    if not result.faces:
        return EncodingResult(embedding=None, num_faces=result.num_faces)
    return EncodingResult(
        embedding=result.faces[0].embedding,
        num_faces=result.num_faces,
    )


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity for L2-normalized embeddings (higher = more alike)."""
    return float(np.dot(a, b))


def euclidean_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Euclidean distance between two face embeddings."""
    return float(np.linalg.norm(a - b))

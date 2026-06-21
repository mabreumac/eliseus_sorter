"""Cluster-based sort: discover people in a batch and copy photos to Person_X folders."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from benchmark_metrics import SortRuntime
from clustering import FaceClusterer, person_id_label
from config import MATCH_TOLERANCE, SORT_LOG_NAME, UNMATCHED_FOLDER
from embeddings import encode_faces_from_path
from group_photos import GroupPhotoMode, GroupPhotoSettings
from image_utils import iter_test_subset_images
from match_subset import (
    NO_FACE_LABEL,
    UNKNOWN_LABEL,
    MatchResult,
    ProgressCallback,
    CancelCallback,
    is_known_match,
)
from student_sorting import apply_production_sorting

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DetectedFace:
    image_path: Path
    face_index: int
    num_faces: int
    embedding: np.ndarray


@dataclass(frozen=True)
class SortConfig:
    input_dir: Path
    output_dir: Path
    tolerance: float = MATCH_TOLERANCE
    group_settings: GroupPhotoSettings = field(default_factory=GroupPhotoSettings)


@dataclass
class SortResult:
    results: list[MatchResult]
    output_dir: Path
    log_path: Optional[Path] = None
    matched_count: int = 0
    unmatched_count: int = 0
    num_clusters: int = 0
    runtime: SortRuntime = field(default_factory=SortRuntime)


def _encoding_mode_for_clustering(_settings: GroupPhotoSettings) -> GroupPhotoMode:
    """Encode every face so clusters reflect all people in the batch."""
    return GroupPhotoMode.ALL_FACES


def _file_group_to_person_folders(settings: GroupPhotoSettings) -> bool:
    return settings.mode == GroupPhotoMode.ALL_FACES


def extract_faces_from_image(
    image_path: Path,
    encoding_mode: GroupPhotoMode,
) -> tuple[list[DetectedFace], Optional[str]]:
    encoding = encode_faces_from_path(image_path, encoding_mode)
    if encoding.error:
        return [], encoding.error

    faces = [
        DetectedFace(
            image_path=image_path,
            face_index=face.face_index,
            num_faces=encoding.num_faces,
            embedding=face.embedding,
        )
        for face in encoding.faces
    ]
    return faces, None


def _build_sort_results(
    image_path: Path,
    faces: list[DetectedFace],
    cluster_assignments: dict[tuple[str, int], tuple[int, float]],
    settings: GroupPhotoSettings,
    error: Optional[str] = None,
) -> list[MatchResult]:
    resolved = str(image_path.resolve())
    num_faces = faces[0].num_faces if faces else 0
    is_group = num_faces > 1
    group_folder = settings.resolved_group_output_folder()

    if error:
        return [
            MatchResult(
                test_file=image_path.name,
                test_path=resolved,
                matched_student=UNKNOWN_LABEL,
                distance=None,
                num_faces=num_faces,
                error=error,
                is_group_photo=is_group,
            )
        ]

    if num_faces == 0:
        return [
            MatchResult(
                test_file=image_path.name,
                test_path=resolved,
                matched_student=NO_FACE_LABEL,
                distance=None,
                num_faces=0,
                is_group_photo=False,
            )
        ]

    results: list[MatchResult] = []

    if is_group and group_folder:
        results.append(
            MatchResult(
                test_file=image_path.name,
                test_path=resolved,
                matched_student=group_folder,
                distance=None,
                num_faces=num_faces,
                is_group_photo=True,
            )
        )

    if is_group and settings.mode == GroupPhotoMode.SKIP:
        return results

    if is_group and not _file_group_to_person_folders(settings):
        faces_to_file = []
    elif is_group:
        faces_to_file = faces
    else:
        faces_to_file = faces[:1]

    seen_clusters: set[int] = set()
    for face in faces_to_file:
        key = (resolved, face.face_index)
        cluster_index, similarity = cluster_assignments.get(key, (-1, None))
        if cluster_index < 0:
            continue
        if is_group and cluster_index in seen_clusters:
            continue
        seen_clusters.add(cluster_index)
        results.append(
            MatchResult(
                test_file=image_path.name,
                test_path=resolved,
                matched_student=person_id_label(cluster_index),
                distance=1.0 - similarity if similarity is not None else None,
                num_faces=num_faces,
                face_index=face.face_index,
                is_group_photo=is_group,
            )
        )

    if not results and not is_group:
        results.append(
            MatchResult(
                test_file=image_path.name,
                test_path=resolved,
                matched_student=UNKNOWN_LABEL,
                distance=None,
                num_faces=num_faces,
                is_group_photo=False,
            )
        )

    return results


def run_cluster_sort(
    config: SortConfig,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> SortResult:
    """
    Discover people in input_dir via face clustering and copy photos to output_dir.

    Creates output_dir/Person_001/, Person_002/, … plus group and unmatched folders.
    Originals in input_dir are never modified.
    """
    if not config.input_dir.is_dir():
        raise ValueError(f"Input folder does not exist: {config.input_dir}")

    config.output_dir.mkdir(parents=True, exist_ok=True)
    settings = config.group_settings
    encoding_mode = _encoding_mode_for_clustering(settings)

    image_paths = list(iter_test_subset_images(config.input_dir))
    total = len(image_paths)
    if total == 0:
        raise ValueError(f"No images found in {config.input_dir}")

    runtime = SortRuntime(num_images=total)

    # Pass 1 — detect faces in every image.
    per_image_faces: list[tuple[Path, list[DetectedFace], Optional[str]]] = []
    t_scan = time.perf_counter()
    for index, image_path in enumerate(image_paths, start=1):
        if should_cancel and should_cancel():
            break
        if on_progress:
            on_progress(
                "scan",
                index,
                total,
                f"Scanning faces: {image_path.name}",
            )
        faces, error = extract_faces_from_image(image_path, encoding_mode)
        per_image_faces.append((image_path, faces, error))
        if faces:
            runtime.num_images_with_face += 1
            runtime.num_faces_detected += len(faces)
        elif not error:
            runtime.num_images_no_face += 1
    runtime.scan_seconds = time.perf_counter() - t_scan

    # Pass 2 — cluster all detected faces together.
    clusterer = FaceClusterer(similarity_threshold=config.tolerance)
    cluster_assignments: dict[tuple[str, int], tuple[int, float]] = {}
    all_faces = [face for _, faces, err in per_image_faces if not err for face in faces]

    t_cluster = time.perf_counter()
    for index, face in enumerate(all_faces, start=1):
        if should_cancel and should_cancel():
            break
        if on_progress and all_faces:
            on_progress(
                "cluster",
                index,
                len(all_faces),
                f"Clustering face {index}/{len(all_faces)}",
            )
        key = (str(face.image_path.resolve()), face.face_index)
        cluster_index, similarity = clusterer.assign(face.embedding)
        cluster_assignments[key] = (cluster_index, similarity)
    runtime.cluster_seconds = time.perf_counter() - t_cluster

    # Pass 3 — build copy plan and write files.
    raw_results: list[MatchResult] = []
    t_copy = time.perf_counter()
    for index, (image_path, faces, error) in enumerate(per_image_faces, start=1):
        if should_cancel and should_cancel():
            break
        if on_progress:
            on_progress(
                "sort",
                index,
                total,
                f"Sorting: {image_path.name}",
            )
        raw_results.extend(
            _build_sort_results(
                image_path, faces, cluster_assignments, settings, error=error
            )
        )

    if not raw_results:
        runtime.copy_seconds = time.perf_counter() - t_copy
        return SortResult(results=[], output_dir=config.output_dir, num_clusters=0, runtime=runtime)

    results = apply_production_sorting(raw_results, config.output_dir)
    runtime.copy_seconds = time.perf_counter() - t_copy

    from reporting import results_to_dataframe

    log_path = config.output_dir / SORT_LOG_NAME
    df = results_to_dataframe(results)
    df.to_csv(log_path, index=False)

    matched = sum(1 for r in results if is_known_match(r.matched_student))
    return SortResult(
        results=results,
        output_dir=config.output_dir,
        log_path=log_path,
        matched_count=matched,
        unmatched_count=len(results) - matched,
        num_clusters=clusterer.num_clusters,
        runtime=runtime,
    )

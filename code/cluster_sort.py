"""Cluster-based sort: class folders with person subfolders, or flat Person_X mode."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from sort_runtime import SortRuntime
from class_registry import ClassRegistry
from clustering import FaceClusterer, person_id_label
from config import (
    CLASS_PHOTOS_FOLDER,
    DEFAULT_MIN_CLASS_FACES,
    DEFAULT_NAMING_REFERENCE_SKIP,
    DEFAULT_SCAN_WORKERS,
    GROUP_OUTPUT_FOLDER,
    MATCH_TOLERANCE,
    SORT_LOG_NAME,
    UNMATCHED_FOLDER,
)
from embeddings import encode_faces_from_path
from face_scan import scan_all_images
from group_photos import GroupPhotoMode, GroupPhotoSettings
from image_utils import iter_sort_input_images
from match_subset import (
    NO_FACE_LABEL,
    UNKNOWN_LABEL,
    MatchResult,
    ProgressCallback,
    CancelCallback,
    is_known_match,
)
from naming_reference import (
    ClusterKey,
    build_naming_index,
    build_person_rename_map,
    resolve_person_label,
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
    min_class_faces: Optional[int] = DEFAULT_MIN_CLASS_FACES
    recursive: bool = True
    naming_reference: Optional[Path] = None
    naming_reference_skip: int = DEFAULT_NAMING_REFERENCE_SKIP
    duplicate_group_photos: bool = False
    scan_workers: int = DEFAULT_SCAN_WORKERS

    def in_place_sort(self) -> bool:
        try:
            return (
                self.input_dir.expanduser().resolve()
                == self.output_dir.expanduser().resolve()
            )
        except OSError:
            return False


@dataclass
class SortResult:
    results: list[MatchResult]
    output_dir: Path
    log_path: Optional[Path] = None
    matched_count: int = 0
    unmatched_count: int = 0
    num_clusters: int = 0
    num_classes: int = 0
    person_renames: dict[str, str] = field(default_factory=dict)
    runtime: SortRuntime = field(default_factory=SortRuntime)


@dataclass
class BatchSortResult:
    runs: list[SortResult]
    output_dir: Path


def discover_input_runs(input_dir: Path) -> list[tuple[str, Path]]:
    """If input has immediate subfolders, each becomes an independent run."""
    if not input_dir.is_dir():
        raise ValueError(f"Input folder does not exist: {input_dir}")
    subdirs = sorted(p for p in input_dir.iterdir() if p.is_dir())
    if subdirs:
        return [(child.name, child) for child in subdirs]
    return [("", input_dir)]


def _iter_images(config: SortConfig) -> list[Path]:
    in_place = config.in_place_sort()
    if config.recursive:
        return list(
            iter_sort_input_images(config.input_dir, recursive=True, in_place=in_place)
        )
    return list(
        iter_sort_input_images(config.input_dir, recursive=False, in_place=in_place)
    )


def _encoding_mode_for_clustering(_settings: GroupPhotoSettings) -> GroupPhotoMode:
    return GroupPhotoMode.ALL_FACES


def _faces_for_person_folders(
    *,
    faces: list[DetectedFace],
    is_group: bool,
    is_class: bool,
    duplicate_group_photos: bool,
) -> list[DetectedFace]:
    if is_class:
        return faces if duplicate_group_photos else []
    if is_group:
        return faces if duplicate_group_photos else []
    return faces[:1]


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


def _scan_all_faces(
    image_paths: list[Path],
    encoding_mode: GroupPhotoMode,
    runtime: SortRuntime,
    *,
    scan_workers: int = DEFAULT_SCAN_WORKERS,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> list[tuple[Path, list[DetectedFace], Optional[str]]]:
    scanned = scan_all_images(
        image_paths,
        encoding_mode,
        workers=scan_workers,
        on_progress=on_progress,
        should_cancel=should_cancel,
    )
    per_image_faces: list[tuple[Path, list[DetectedFace], Optional[str]]] = []
    for image_path, face_rows, error in scanned:
        if error:
            per_image_faces.append((image_path, [], error))
            continue
        faces = [
            DetectedFace(
                image_path=image_path,
                face_index=face_index,
                num_faces=num_faces,
                embedding=embedding,
            )
            for face_index, num_faces, embedding in face_rows
        ]
        per_image_faces.append((image_path, faces, None))
        if faces:
            runtime.num_images_with_face += 1
            runtime.num_faces_detected += len(faces)
        else:
            runtime.num_images_no_face += 1
    return per_image_faces


def _is_class_photo(num_faces: int, min_class_faces: int) -> bool:
    return num_faces > min_class_faces


def _gather_flat_cluster_embeddings(
    all_faces: list[DetectedFace],
    cluster_assignments: dict[tuple[str, int], tuple[int, float]],
) -> dict[ClusterKey, list[np.ndarray]]:
    buckets: dict[ClusterKey, list[np.ndarray]] = {}
    for face in all_faces:
        key = (str(face.image_path.resolve()), face.face_index)
        cluster_index, _ = cluster_assignments.get(key, (-1, 0.0))
        if cluster_index < 0:
            continue
        bucket_key: ClusterKey = (None, cluster_index)
        buckets.setdefault(bucket_key, []).append(face.embedding)
    return buckets


def _gather_class_cluster_embeddings(
    per_image_faces: list[tuple[Path, list[DetectedFace], Optional[str]]],
    face_assignments: dict[tuple[str, int], tuple[str, int, float]],
) -> dict[ClusterKey, list[np.ndarray]]:
    buckets: dict[ClusterKey, list[np.ndarray]] = {}
    for image_path, faces, error in per_image_faces:
        if error:
            continue
        resolved = str(image_path.resolve())
        for face in faces:
            assignment = face_assignments.get((resolved, face.face_index))
            if not assignment:
                continue
            cls_label, cluster_index, _ = assignment
            bucket_key: ClusterKey = (cls_label, cluster_index)
            buckets.setdefault(bucket_key, []).append(face.embedding)
    return buckets


def _resolve_person_renames(
    config: SortConfig,
    cluster_embeddings: dict[ClusterKey, list[np.ndarray]],
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> dict[ClusterKey, str]:
    if config.naming_reference is None:
        return {}
    ref_path = config.naming_reference.expanduser().resolve()
    index = build_naming_index(
        ref_path,
        skip_levels=config.naming_reference_skip,
        workers=config.scan_workers,
        on_progress=on_progress,
        should_cancel=should_cancel,
    )
    return build_person_rename_map(
        cluster_embeddings,
        index,
        config.tolerance,
        on_progress=on_progress,
    )


def _rename_log(rename_map: dict[ClusterKey, str]) -> dict[str, str]:
    logged: dict[str, str] = {}
    for (class_folder, cluster_index), name in rename_map.items():
        label = person_id_label(cluster_index)
        key = f"{class_folder}/{label}" if class_folder else label
        logged[key] = name
    return logged


def _build_flat_sort_results(
    image_path: Path,
    faces: list[DetectedFace],
    cluster_assignments: dict[tuple[str, int], tuple[int, float]],
    settings: GroupPhotoSettings,
    *,
    duplicate_group_photos: bool = False,
    rename_map: dict[ClusterKey, str] | None = None,
    error: Optional[str] = None,
) -> list[MatchResult]:
    rename_map = rename_map or {}
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

    faces_to_file = _faces_for_person_folders(
        faces=faces,
        is_group=is_group,
        is_class=False,
        duplicate_group_photos=duplicate_group_photos,
    )

    seen_clusters: set[int] = set()
    for face in faces_to_file:
        key = (resolved, face.face_index)
        cluster_index, similarity = cluster_assignments.get(key, (-1, None))
        if cluster_index < 0:
            continue
        if is_group and cluster_index in seen_clusters:
            continue
        seen_clusters.add(cluster_index)
        person_label = resolve_person_label(
            cluster_index, None, rename_map, person_id_label(cluster_index)
        )
        results.append(
            MatchResult(
                test_file=image_path.name,
                test_path=resolved,
                matched_student=person_label,
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


def _dominant_class(
    faces: list[DetectedFace],
    face_assignments: dict[tuple[str, int], tuple[str, int, float]],
) -> Optional[str]:
    counts: dict[str, int] = {}
    resolved = str(faces[0].image_path.resolve()) if faces else ""
    for face in faces:
        hit = face_assignments.get((resolved, face.face_index))
        if hit:
            counts[hit[0]] = counts.get(hit[0], 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def _build_class_sort_results(
    image_path: Path,
    faces: list[DetectedFace],
    face_assignments: dict[tuple[str, int], tuple[str, int, float]],
    registry: ClassRegistry,
    min_class_faces: int,
    settings: GroupPhotoSettings,
    *,
    duplicate_group_photos: bool = False,
    rename_map: dict[ClusterKey, str] | None = None,
    error: Optional[str] = None,
) -> list[MatchResult]:
    rename_map = rename_map or {}
    resolved = str(image_path.resolve())
    num_faces = faces[0].num_faces if faces else 0
    is_group = num_faces > 1
    is_class = _is_class_photo(num_faces, min_class_faces)
    class_label = registry.class_for_photo(image_path)
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

    if is_class and class_label:
        results.append(
            MatchResult(
                test_file=image_path.name,
                test_path=resolved,
                matched_student=CLASS_PHOTOS_FOLDER,
                distance=None,
                num_faces=num_faces,
                is_group_photo=True,
                is_class_photo=True,
                class_folder=class_label,
            )
        )

    if is_group and not is_class and group_folder:
        dominant = _dominant_class(faces, face_assignments)
        results.append(
            MatchResult(
                test_file=image_path.name,
                test_path=resolved,
                matched_student=group_folder,
                distance=None,
                num_faces=num_faces,
                is_group_photo=True,
                class_folder=dominant,
            )
        )

    faces_to_file = _faces_for_person_folders(
        faces=faces,
        is_group=is_group,
        is_class=is_class,
        duplicate_group_photos=duplicate_group_photos,
    )
    seen_person: set[tuple[str, int]] = set()
    for face in faces_to_file:
        key = (resolved, face.face_index)
        assignment = face_assignments.get(key)
        if not assignment:
            continue
        cls_label, cluster_index, similarity = assignment
        person_key = (cls_label, cluster_index)
        if is_group and person_key in seen_person:
            continue
        seen_person.add(person_key)
        person_label = resolve_person_label(
            cluster_index, cls_label, rename_map, person_id_label(cluster_index)
        )
        results.append(
            MatchResult(
                test_file=image_path.name,
                test_path=resolved,
                matched_student=person_label,
                distance=1.0 - similarity,
                num_faces=num_faces,
                face_index=face.face_index,
                is_group_photo=is_group,
                class_folder=cls_label,
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


def _run_flat_sort(
    config: SortConfig,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> SortResult:
    settings = config.group_settings
    encoding_mode = _encoding_mode_for_clustering(settings)
    image_paths = _iter_images(config)
    total = len(image_paths)
    if total == 0:
        raise ValueError(f"No images found in {config.input_dir}")

    runtime = SortRuntime(num_images=total)
    t_scan = time.perf_counter()
    per_image_faces = _scan_all_faces(
        image_paths,
        encoding_mode,
        runtime,
        scan_workers=config.scan_workers,
        on_progress=on_progress,
        should_cancel=should_cancel,
    )
    runtime.scan_seconds = time.perf_counter() - t_scan

    clusterer = FaceClusterer(similarity_threshold=config.tolerance)
    cluster_assignments: dict[tuple[str, int], tuple[int, float]] = {}
    all_faces = [face for _, faces, err in per_image_faces if not err for face in faces]

    t_cluster = time.perf_counter()
    for index, face in enumerate(all_faces, start=1):
        if should_cancel and should_cancel():
            break
        if on_progress and all_faces:
            on_progress("cluster", index, len(all_faces), f"Clustering face {index}/{len(all_faces)}")
        key = (str(face.image_path.resolve()), face.face_index)
        cluster_index, similarity = clusterer.assign(face.embedding)
        cluster_assignments[key] = (cluster_index, similarity)
    runtime.cluster_seconds = time.perf_counter() - t_cluster

    rename_map = _resolve_person_renames(
        config,
        _gather_flat_cluster_embeddings(all_faces, cluster_assignments),
        on_progress,
        should_cancel,
    )

    raw_results: list[MatchResult] = []
    t_copy = time.perf_counter()
    for index, (image_path, faces, error) in enumerate(per_image_faces, start=1):
        if should_cancel and should_cancel():
            break
        if on_progress:
            on_progress("sort", index, total, f"Sorting: {image_path.name}")
        raw_results.extend(
            _build_flat_sort_results(
                image_path,
                faces,
                cluster_assignments,
                settings,
                duplicate_group_photos=config.duplicate_group_photos,
                rename_map=rename_map,
                error=error,
            )
        )

    if not raw_results:
        runtime.copy_seconds = time.perf_counter() - t_copy
        return SortResult(results=[], output_dir=config.output_dir, runtime=runtime)

    results = apply_production_sorting(
        raw_results,
        config.output_dir,
        in_place=config.in_place_sort(),
    )
    runtime.copy_seconds = time.perf_counter() - t_copy

    from reporting import results_to_dataframe

    log_path = config.output_dir / SORT_LOG_NAME
    results_to_dataframe(results).to_csv(log_path, index=False)

    matched = sum(1 for r in results if is_known_match(r.matched_student))
    return SortResult(
        results=results,
        output_dir=config.output_dir,
        log_path=log_path,
        matched_count=matched,
        unmatched_count=len(results) - matched,
        num_clusters=clusterer.num_clusters,
        person_renames=_rename_log(rename_map),
        runtime=runtime,
    )


def _run_class_sort(
    config: SortConfig,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> SortResult:
    if config.min_class_faces is None:
        raise ValueError("min_class_faces is required for class sorting")

    min_class_faces = config.min_class_faces
    settings = config.group_settings
    encoding_mode = _encoding_mode_for_clustering(settings)
    image_paths = _iter_images(config)
    total = len(image_paths)
    if total == 0:
        raise ValueError(f"No images found in {config.input_dir}")

    runtime = SortRuntime(num_images=total)
    t_scan = time.perf_counter()
    per_image_faces = _scan_all_faces(
        image_paths,
        encoding_mode,
        runtime,
        scan_workers=config.scan_workers,
        on_progress=on_progress,
        should_cancel=should_cancel,
    )
    runtime.scan_seconds = time.perf_counter() - t_scan

    class_photos = [
        (path, faces)
        for path, faces, err in per_image_faces
        if not err and _is_class_photo(len(faces), min_class_faces)
    ]
    if not class_photos:
        raise ValueError(
            f"No class photos found — need at least one photo with more than "
            f"{min_class_faces} faces (try lowering the class face threshold)."
        )

    registry = ClassRegistry(similarity_threshold=config.tolerance)
    class_photo_paths: set[Path] = set()

    t_cluster = time.perf_counter()
    for photo_path, faces in sorted(class_photos, key=lambda item: item[0].name):
        embeddings = [(face.face_index, face.embedding) for face in faces]
        registry.register_class_photo(photo_path, embeddings)
        class_photo_paths.add(photo_path)

    face_assignments: dict[tuple[str, int], tuple[str, int, float]] = {}
    for bucket in registry.classes:
        face_assignments.update(
            (key, (bucket.label, cluster_index, similarity))
            for key, (cluster_index, similarity) in bucket.seed_assignments.items()
        )

    other_faces = [
        face
        for path, faces, err in per_image_faces
        if not err and path not in class_photo_paths
        for face in faces
    ]
    for index, face in enumerate(other_faces, start=1):
        if should_cancel and should_cancel():
            break
        if on_progress and other_faces:
            on_progress(
                "cluster",
                index,
                len(other_faces),
                f"Matching face {index}/{len(other_faces)}",
            )
        key = (str(face.image_path.resolve()), face.face_index)
        cls_label, cluster_index, similarity = registry.assign_face(face.embedding)
        if cls_label is not None and cluster_index is not None:
            face_assignments[key] = (cls_label, cluster_index, similarity)

    runtime.cluster_seconds = time.perf_counter() - t_cluster

    rename_map = _resolve_person_renames(
        config,
        _gather_class_cluster_embeddings(per_image_faces, face_assignments),
        on_progress,
        should_cancel,
    )

    raw_results: list[MatchResult] = []
    t_copy = time.perf_counter()
    for index, (image_path, faces, error) in enumerate(per_image_faces, start=1):
        if should_cancel and should_cancel():
            break
        if on_progress:
            on_progress("sort", index, total, f"Sorting: {image_path.name}")
        raw_results.extend(
            _build_class_sort_results(
                image_path,
                faces,
                face_assignments,
                registry,
                min_class_faces,
                settings,
                duplicate_group_photos=config.duplicate_group_photos,
                rename_map=rename_map,
                error=error,
            )
        )

    if not raw_results:
        runtime.copy_seconds = time.perf_counter() - t_copy
        return SortResult(
            results=[],
            output_dir=config.output_dir,
            num_classes=registry.num_classes,
            runtime=runtime,
        )

    results = apply_production_sorting(
        raw_results,
        config.output_dir,
        in_place=config.in_place_sort(),
    )
    runtime.copy_seconds = time.perf_counter() - t_copy

    from reporting import results_to_dataframe

    log_path = config.output_dir / SORT_LOG_NAME
    results_to_dataframe(results).to_csv(log_path, index=False)

    matched = sum(1 for r in results if is_known_match(r.matched_student))
    num_clusters = sum(bucket.clusterer.num_clusters for bucket in registry.classes)
    return SortResult(
        results=results,
        output_dir=config.output_dir,
        log_path=log_path,
        matched_count=matched,
        unmatched_count=len(results) - matched,
        num_clusters=num_clusters,
        num_classes=registry.num_classes,
        person_renames=_rename_log(rename_map),
        runtime=runtime,
    )


def run_cluster_sort(
    config: SortConfig,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> SortResult:
    """Discover people and copy photos into class/Person folders (or flat Person_X mode)."""
    config.output_dir.mkdir(parents=True, exist_ok=True)
    if config.min_class_faces is None:
        return _run_flat_sort(config, on_progress, should_cancel)
    return _run_class_sort(config, on_progress, should_cancel)


def run_batch_sort(
    config: SortConfig,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> BatchSortResult | SortResult:
    """Run one or more independent sorts when input contains subfolders."""
    runs = discover_input_runs(config.input_dir)
    if len(runs) == 1 and runs[0][0] == "":
        return run_cluster_sort(config, on_progress, should_cancel)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    results: list[SortResult] = []
    for run_index, (name, input_path) in enumerate(runs, start=1):
        if should_cancel and should_cancel():
            break
        run_output = config.output_dir / f"run_{name}"
        run_config = replace(config, input_dir=input_path, output_dir=run_output)

        def run_progress(phase: str, current: int, total: int, message: str) -> None:
            if on_progress:
                on_progress(
                    phase,
                    current,
                    total,
                    f"[{name}] {message} ({run_index}/{len(runs)})",
                )

        results.append(
            run_cluster_sort(run_config, on_progress=run_progress, should_cancel=should_cancel)
        )

    return BatchSortResult(runs=results, output_dir=config.output_dir)

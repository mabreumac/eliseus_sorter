"""Cluster-based sort: class folders with person subfolders, or flat Person_X mode."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from sort_runtime import SortCancelled, SortRuntime

SORT_COMPLETE_MARKER = ".sort_complete"
from class_registry import ClassRegistry, class_id_label
from clustering import FaceClusterer, format_person_folder_label, person_id_label
from config import (
    CLASS_PHOTOS_FOLDER,
    DEFAULT_FACE_SENSITIVITY,
    DEFAULT_MIN_CLASS_FACES,
    DEFAULT_MOVE_FILES,
    DEFAULT_NAMING_REFERENCE_SKIP,
    DEFAULT_SCAN_WORKERS,
    GROUP_OUTPUT_FOLDER,
    MATCH_TOLERANCE,
    NO_CLASS_FOLDER,
    SORT_LOG_NAME,
    SORT_RUN_FOLDER_SUFFIX,
    UNMATCHED_FOLDER,
)
from embeddings import FaceFilterParams, encode_faces_from_path
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
from person_order import (
    build_person_order,
    collect_class_cluster_appearances,
    collect_flat_cluster_appearances,
    image_path_order_index,
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
    move_files: bool = DEFAULT_MOVE_FILES
    face_sensitivity: int = DEFAULT_FACE_SENSITIVITY

    def face_filter(self) -> FaceFilterParams:
        return FaceFilterParams.from_sensitivity(self.face_sensitivity)

    def skip_sort_outputs_when_scanning(self, effective_output: Path) -> bool:
        """Skip prior sort folders under input when output overlaps the input tree."""
        try:
            inp = self.input_dir.expanduser().resolve()
            out = effective_output.expanduser().resolve()
            if inp == out:
                return True
            out.relative_to(inp)
            return True
        except (OSError, ValueError):
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


def input_has_subfolders(input_dir: Path) -> bool:
    """True when input contains at least one subdirectory (nested batch layout)."""
    if not input_dir.is_dir():
        return False
    return any(path.is_dir() for path in input_dir.iterdir())


def resolve_sort_output_dir(input_dir: Path, output_dir: Path) -> Path:
    """Write each run into a fresh timestamped folder under output."""
    del input_dir  # kept for call-site compatibility
    base = output_dir.expanduser().resolve()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return base / f"{stamp}{SORT_RUN_FOLDER_SUFFIX}"


def discover_input_runs(input_dir: Path) -> list[tuple[str, Path]]:
    """Deprecated: sorting now treats the full input tree as one pool."""
    if not input_dir.is_dir():
        raise ValueError(f"Input folder does not exist: {input_dir}")
    return [("", input_dir)]


def _raise_if_cancelled(should_cancel: Optional[CancelCallback]) -> None:
    if should_cancel and should_cancel():
        raise SortCancelled()


def _iter_images(config: SortConfig, effective_output: Path) -> list[Path]:
    skip_outputs = config.skip_sort_outputs_when_scanning(effective_output)
    if config.recursive:
        return list(
            iter_sort_input_images(
                config.input_dir,
                recursive=True,
                skip_sort_outputs=skip_outputs,
            )
        )
    return list(
        iter_sort_input_images(
            config.input_dir,
            recursive=False,
            skip_sort_outputs=skip_outputs,
        )
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
    face_filter: FaceFilterParams | None = None,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> list[tuple[Path, list[DetectedFace], Optional[str]]]:
    scanned = scan_all_images(
        image_paths,
        encoding_mode,
        workers=scan_workers,
        face_filter=face_filter,
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


def _image_face_count(faces: list[DetectedFace]) -> int:
    """Detected face count for one image (after background filter)."""
    if not faces:
        return 0
    return faces[0].num_faces


def _class_photo_candidates(
    per_image_faces: list[tuple[Path, list[DetectedFace], Optional[str]]],
    min_class_faces: int,
) -> list[tuple[Path, list[DetectedFace]]]:
    return [
        (path, faces)
        for path, faces, err in per_image_faces
        if not err and _is_class_photo(_image_face_count(faces), min_class_faces)
    ]


def _count_roster_classes(
    class_photos: list[tuple[Path, list[DetectedFace]]],
    tolerance: float,
) -> int:
    """How many distinct classes roster photos define (same logic as full class sort)."""
    if not class_photos:
        return 0
    registry = ClassRegistry(similarity_threshold=tolerance)
    for photo_path, faces in sorted(class_photos, key=lambda item: item[0].name):
        embeddings = [(face.face_index, face.embedding) for face in faces]
        registry.register_class_photo(photo_path, embeddings)
    return registry.num_classes


def _scan_input(
    config: SortConfig,
    *,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> tuple[list[Path], list[tuple[Path, list[DetectedFace], Optional[str]]], SortRuntime]:
    encoding_mode = _encoding_mode_for_clustering(config.group_settings)
    image_paths = _iter_images(config, config.output_dir)
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
        face_filter=config.face_filter(),
        on_progress=on_progress,
        should_cancel=should_cancel,
    )
    runtime.scan_seconds = time.perf_counter() - t_scan
    _raise_if_cancelled(should_cancel)
    return image_paths, per_image_faces, runtime


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
        face_filter=config.face_filter(),
        on_progress=on_progress,
        should_cancel=should_cancel,
    )
    if index.loaded_from_cache:
        logger.info("Naming reference loaded from cache (%d identities)", len(index.references))
    for warning in index.duplicate_name_warnings:
        logger.warning(warning)
    return build_person_rename_map(
        cluster_embeddings,
        index,
        config.tolerance,
        on_progress=on_progress,
    )


def _rename_log(
    rename_map: dict[ClusterKey, str],
    person_order_remap: dict[ClusterKey, int] | None = None,
) -> dict[str, str]:
    logged: dict[str, str] = {}
    for (class_folder, cluster_index), name in rename_map.items():
        key = (class_folder, cluster_index)
        if person_order_remap is not None and key in person_order_remap:
            label = format_person_folder_label(person_order_remap[key], name)
        else:
            label = format_person_folder_label(cluster_index, name)
        log_key = f"{class_folder}/{label}" if class_folder else label
        logged[log_key] = label
    return logged


def _build_flat_sort_results(
    image_path: Path,
    faces: list[DetectedFace],
    cluster_assignments: dict[tuple[str, int], tuple[int, float]],
    settings: GroupPhotoSettings,
    *,
    duplicate_group_photos: bool = False,
    rename_map: dict[ClusterKey, str] | None = None,
    person_order_remap: dict[ClusterKey, int] | None = None,
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
            cluster_index,
            None,
            rename_map,
            person_id_label(cluster_index),
            person_order_remap=person_order_remap,
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
    person_order_remap: dict[ClusterKey, int] | None = None,
    single_class_label: Optional[str] = None,
    error: Optional[str] = None,
) -> list[MatchResult]:
    rename_map = rename_map or {}
    resolved = str(image_path.resolve())
    num_faces = faces[0].num_faces if faces else 0
    is_group = num_faces > 1
    is_class = _is_class_photo(num_faces, min_class_faces)
    class_label = registry.class_for_photo(image_path) or single_class_label
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
            cluster_index,
            cls_label,
            rename_map,
            person_id_label(cluster_index),
            person_order_remap=person_order_remap,
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
    image_paths = _iter_images(config, config.output_dir)
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
        face_filter=config.face_filter(),
        on_progress=on_progress,
        should_cancel=should_cancel,
    )
    runtime.scan_seconds = time.perf_counter() - t_scan
    _raise_if_cancelled(should_cancel)

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
    _raise_if_cancelled(should_cancel)

    rename_map = _resolve_person_renames(
        config,
        _gather_flat_cluster_embeddings(all_faces, cluster_assignments),
        on_progress,
        should_cancel,
    )

    path_order = image_path_order_index(image_paths)
    person_order_remap = build_person_order(
        cluster_appearances=collect_flat_cluster_appearances(
            path_order=path_order,
            per_image_faces=per_image_faces,
            cluster_assignments=cluster_assignments,
        ),
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
                person_order_remap=person_order_remap,
                error=error,
            )
        )

    _raise_if_cancelled(should_cancel)

    if not raw_results:
        runtime.copy_seconds = time.perf_counter() - t_copy
        return SortResult(results=[], output_dir=config.output_dir, runtime=runtime)

    results = apply_production_sorting(
        raw_results,
        config.output_dir,
        move_files=config.move_files,
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
        person_renames=_rename_log(rename_map, person_order_remap),
        runtime=runtime,
    )


def _run_single_class_sort(
    config: SortConfig,
    image_paths: list[Path],
    per_image_faces: list[tuple[Path, list[DetectedFace], Optional[str]]],
    runtime: SortRuntime,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> SortResult:
    """One class folder for the whole batch — no roster / class photos required."""
    min_class_faces = config.min_class_faces
    if min_class_faces is None:
        min_class_faces = DEFAULT_MIN_CLASS_FACES

    single_class = class_id_label(0)
    settings = config.group_settings
    total = len(image_paths)

    if on_progress:
        on_progress("cluster", 0, 1, "Single class — grouping whole batch as class_001")

    clusterer = FaceClusterer(similarity_threshold=config.tolerance)
    face_assignments: dict[tuple[str, int], tuple[str, int, float]] = {}
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
        face_assignments[key] = (single_class, cluster_index, similarity)
    runtime.cluster_seconds = time.perf_counter() - t_cluster
    _raise_if_cancelled(should_cancel)

    registry = ClassRegistry(similarity_threshold=config.tolerance)

    rename_map = _resolve_person_renames(
        config,
        _gather_class_cluster_embeddings(per_image_faces, face_assignments),
        on_progress,
        should_cancel,
    )

    path_order = image_path_order_index(image_paths)
    person_order_remap = build_person_order(
        cluster_appearances=collect_class_cluster_appearances(
            path_order=path_order,
            per_image_faces=per_image_faces,
            face_assignments=face_assignments,
        ),
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
                person_order_remap=person_order_remap,
                single_class_label=single_class,
                error=error,
            )
        )

    _raise_if_cancelled(should_cancel)

    if not raw_results:
        runtime.copy_seconds = time.perf_counter() - t_copy
        return SortResult(
            results=[],
            output_dir=config.output_dir,
            num_classes=1,
            runtime=runtime,
        )

    results = apply_production_sorting(
        raw_results,
        config.output_dir,
        move_files=config.move_files,
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
        num_classes=1,
        person_renames=_rename_log(rename_map, person_order_remap),
        runtime=runtime,
    )


def _run_class_sort(
    config: SortConfig,
    image_paths: list[Path],
    per_image_faces: list[tuple[Path, list[DetectedFace], Optional[str]]],
    runtime: SortRuntime,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> SortResult:
    if config.min_class_faces is None:
        raise ValueError("min_class_faces is required for class sorting")

    min_class_faces = config.min_class_faces
    settings = config.group_settings
    total = len(image_paths)

    class_photos = _class_photo_candidates(per_image_faces, min_class_faces)
    if not class_photos:
        raise ValueError("Internal error: multi-class sort without roster photos")

    if on_progress:
        on_progress(
            "cluster",
            0,
            1,
            f"Multi-class — {len(class_photos)} roster photo(s) detected",
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

    unassigned_faces = [
        face
        for face in other_faces
        if (str(face.image_path.resolve()), face.face_index) not in face_assignments
    ]
    no_class_clusterer = FaceClusterer(similarity_threshold=config.tolerance)
    for index, face in enumerate(unassigned_faces, start=1):
        if should_cancel and should_cancel():
            break
        if on_progress and unassigned_faces:
            on_progress(
                "cluster",
                index,
                len(unassigned_faces),
                f"Clustering unassigned face {index}/{len(unassigned_faces)}",
            )
        key = (str(face.image_path.resolve()), face.face_index)
        cluster_index, similarity = no_class_clusterer.assign(face.embedding)
        face_assignments[key] = (NO_CLASS_FOLDER, cluster_index, similarity)

    runtime.cluster_seconds = time.perf_counter() - t_cluster
    _raise_if_cancelled(should_cancel)

    rename_map = _resolve_person_renames(
        config,
        _gather_class_cluster_embeddings(per_image_faces, face_assignments),
        on_progress,
        should_cancel,
    )

    path_order = image_path_order_index(image_paths)
    person_order_remap = build_person_order(
        cluster_appearances=collect_class_cluster_appearances(
            path_order=path_order,
            per_image_faces=per_image_faces,
            face_assignments=face_assignments,
        ),
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
                person_order_remap=person_order_remap,
                error=error,
            )
        )

    _raise_if_cancelled(should_cancel)

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
        move_files=config.move_files,
    )
    runtime.copy_seconds = time.perf_counter() - t_copy

    from reporting import results_to_dataframe

    log_path = config.output_dir / SORT_LOG_NAME
    results_to_dataframe(results).to_csv(log_path, index=False)

    matched = sum(1 for r in results if is_known_match(r.matched_student))
    num_clusters = sum(bucket.clusterer.num_clusters for bucket in registry.classes)
    num_clusters += no_class_clusterer.num_clusters
    return SortResult(
        results=results,
        output_dir=config.output_dir,
        log_path=log_path,
        matched_count=matched,
        unmatched_count=len(results) - matched,
        num_clusters=num_clusters,
        num_classes=registry.num_classes,
        person_renames=_rename_log(rename_map, person_order_remap),
        runtime=runtime,
    )


def run_cluster_sort(
    config: SortConfig,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> SortResult:
    """Discover people and copy photos into class/person folders (or flat mode)."""
    config.output_dir.mkdir(parents=True, exist_ok=True)
    if config.min_class_faces is None:
        return _run_flat_sort(config, on_progress, should_cancel)

    min_class_faces = config.min_class_faces
    image_paths, per_image_faces, runtime = _scan_input(
        config, on_progress=on_progress, should_cancel=should_cancel
    )
    roster_class_count = _count_roster_classes(
        _class_photo_candidates(per_image_faces, min_class_faces),
        config.tolerance,
    )
    logger.info(
        "Roster analysis: %d class(es) detected (threshold > %d faces)",
        roster_class_count,
        min_class_faces,
    )

    if roster_class_count < 2:
        return _run_single_class_sort(
            config,
            image_paths,
            per_image_faces,
            runtime,
            on_progress,
            should_cancel,
        )
    return _run_class_sort(
        config,
        image_paths,
        per_image_faces,
        runtime,
        on_progress,
        should_cancel,
    )


def run_batch_sort(
    config: SortConfig,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> SortResult:
    """Sort all images under input as one pool into the resolved output folder."""
    effective_output = resolve_sort_output_dir(config.input_dir, config.output_dir)
    effective_config = replace(config, output_dir=effective_output)
    result = run_cluster_sort(effective_config, on_progress, should_cancel)
    (effective_output / SORT_COMPLETE_MARKER).write_text(
        datetime.now().isoformat(timespec="seconds"),
        encoding="utf-8",
    )
    return result

"""Optional naming_reference: match Person_XXX clusters to named folders."""

from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from config import MATCH_TOLERANCE, NO_CLASS_FOLDER
from embeddings import FaceFilterParams, cosine_similarity, encode_faces_from_path, normalize_embedding
from face_scan import CancelCallback, ProgressCallback, effective_scan_workers, init_scan_worker
from group_photos import GroupPhotoMode, is_group_reference_folder
from image_utils import iter_images_recursive

logger = logging.getLogger(__name__)

ClusterKey = tuple[Optional[str], int]  # (class_folder or None, cluster_index)


@dataclass
class NamedReference:
    name: str
    centroid: np.ndarray
    folder: Path
    sample_count: int = 1
    source_image: Optional[Path] = None


@dataclass
class NamingIndex:
    references: list[NamedReference] = field(default_factory=list)
    skipped_multi_face: int = 0
    skipped_no_face: int = 0
    skipped_empty_folders: int = 0
    duplicate_name_warnings: list[str] = field(default_factory=list)
    loaded_from_cache: bool = False


def _centroid(embeddings: list[np.ndarray]) -> np.ndarray:
    stacked = np.stack([normalize_embedding(e) for e in embeddings], axis=0)
    return normalize_embedding(stacked.mean(axis=0))


def _is_reference_folder(name: str) -> bool:
    lowered = name.strip().casefold()
    if lowered.startswith("person_"):
        return False
    if lowered.startswith("class_"):
        return False
    if is_group_reference_folder(name):
        return False
    if lowered in {
        "_unmatched",
        NO_CLASS_FOLDER,
        "_class_photos",
        "_group_photos",
        "group_photos",
    }:
        return False
    return True


def _name_folder_for_image(image_path: Path, root: Path, skip_levels: int) -> Optional[Path]:
    """
    From each photo, walk up skip_levels folders above the photo's parent directory.
    That folder's name is the student name (works at any depth under root).
    """
    if skip_levels < 0:
        raise ValueError("Naming reference skip levels must be 0 or greater.")

    root = root.resolve()
    folder = image_path.parent.resolve()
    try:
        folder.relative_to(root)
    except ValueError:
        return None

    for _ in range(skip_levels):
        folder = folder.parent
        if folder == root:
            return None
        try:
            folder.relative_to(root)
        except ValueError:
            return None

    if folder == root or not _is_reference_folder(folder.name):
        return None
    return folder


def _student_name_for_image(image_path: Path, root: Path, skip_levels: int) -> Optional[str]:
    folder = _name_folder_for_image(image_path, root, skip_levels)
    return folder.name if folder is not None else None


def _group_images_by_student_name(root: Path, skip_levels: int) -> dict[str, list[Path]]:
    """Bottom-up: discover photos first, derive student name by walking up skip_levels."""
    groups: dict[str, list[Path]] = {}
    for image_path in iter_images_recursive(root):
        name = _student_name_for_image(image_path, root, skip_levels)
        if not name:
            continue
        groups.setdefault(name, []).append(image_path)
    for name in groups:
        groups[name] = sorted(groups[name], key=lambda path: str(path.resolve()))
    return dict(sorted(groups.items()))


def duplicate_name_warnings(root: Path, skip_levels: int) -> list[str]:
    """Warn when the same identity label is derived from more than one folder."""
    root = root.resolve()
    label_folders: dict[str, set[str]] = {}
    for image_path in iter_images_recursive(root):
        name = _student_name_for_image(image_path, root, skip_levels)
        folder = _name_folder_for_image(image_path, root, skip_levels)
        if not name or folder is None:
            continue
        try:
            rel_folder = folder.relative_to(root).as_posix()
        except ValueError:
            rel_folder = str(folder.resolve())
        label_folders.setdefault(name, set()).add(rel_folder)

    warnings: list[str] = []
    for name, folders in sorted(label_folders.items()):
        if len(folders) <= 1:
            continue
        folder_list = ", ".join(sorted(folders)[:6])
        extra = f" (+{len(folders) - 6} more)" if len(folders) > 6 else ""
        warnings.append(
            f"Reference label {name!r} is used in {len(folders)} different folders "
            f"({folder_list}{extra}) — only one face embedding is kept for that label."
        )
    return warnings


def _index_to_cache_payload(index: NamingIndex) -> dict[str, object]:
    return {
        "skipped_multi_face": index.skipped_multi_face,
        "skipped_no_face": index.skipped_no_face,
        "skipped_empty_folders": index.skipped_empty_folders,
        "duplicate_name_warnings": index.duplicate_name_warnings,
        "references": [
            {
                "name": ref.name,
                "centroid": ref.centroid.astype(float).tolist(),
                "folder": str(ref.folder.resolve()),
                "sample_count": ref.sample_count,
                "source_image": str(ref.source_image.resolve()) if ref.source_image else None,
            }
            for ref in index.references
        ],
    }


def _index_from_cache_payload(payload: dict[str, object]) -> NamingIndex:
    references: list[NamedReference] = []
    for item in payload.get("references") or []:
        if not isinstance(item, dict):
            continue
        references.append(
            NamedReference(
                name=str(item["name"]),
                centroid=np.asarray(item["centroid"], dtype=np.float64),
                folder=Path(str(item["folder"])),
                sample_count=int(item.get("sample_count", 1)),
                source_image=Path(str(item["source_image"])) if item.get("source_image") else None,
            )
        )
    warnings_raw = payload.get("duplicate_name_warnings") or []
    return NamingIndex(
        references=references,
        skipped_multi_face=int(payload.get("skipped_multi_face", 0)),
        skipped_no_face=int(payload.get("skipped_no_face", 0)),
        skipped_empty_folders=int(payload.get("skipped_empty_folders", 0)),
        duplicate_name_warnings=[str(w) for w in warnings_raw],
        loaded_from_cache=True,
    )


def _first_single_face_in_images(
    image_paths: list[Path],
    *,
    face_filter: FaceFilterParams | None = None,
) -> tuple[Optional[np.ndarray], Optional[Path], int, int]:
    """Use the first single-face photo in the list; return skip counts."""
    skipped_no_face = 0
    skipped_multi_face = 0
    for image_path in image_paths:
        encoded = encode_faces_from_path(
            image_path,
            GroupPhotoMode.FIRST_FACE,
            face_filter=face_filter,
        )
        if encoded.error:
            continue
        if encoded.num_faces == 0:
            skipped_no_face += 1
            continue
        if encoded.num_faces > 1:
            skipped_multi_face += 1
            continue
        if encoded.faces:
            return encoded.faces[0].embedding, image_path, skipped_no_face, skipped_multi_face
    return None, None, skipped_no_face, skipped_multi_face


def _build_naming_index_fresh(
    root: Path,
    *,
    skip_levels: int,
    workers: int | None,
    filt: FaceFilterParams,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> NamingIndex:
    index = NamingIndex()
    image_groups = _group_images_by_student_name(root, skip_levels)
    total = len(image_groups)
    worker_count = effective_scan_workers(workers)

    if worker_count <= 1:
        for folder_index, (name, image_paths) in enumerate(image_groups.items(), start=1):
            if should_cancel and should_cancel():
                break
            if on_progress:
                on_progress(
                    "naming",
                    folder_index,
                    total,
                    f"Indexing reference: {name}",
                )

            embedding, source_image, skipped_no_face, skipped_multi_face = (
                _first_single_face_in_images(image_paths, face_filter=filt)
            )
            index.skipped_no_face += skipped_no_face
            index.skipped_multi_face += skipped_multi_face
            if embedding is None:
                index.skipped_empty_folders += 1
                logger.warning("No single-face reference photo for student name: %s", name)
                continue

            name_folder = _name_folder_for_image(source_image, root, skip_levels)
            index.references.append(
                NamedReference(
                    name=name,
                    centroid=normalize_embedding(embedding),
                    sample_count=1,
                    source_image=source_image,
                    folder=name_folder or source_image.parent,
                )
            )
            logger.debug("Reference %s from %s", name, source_image)
    else:
        logger.info("Naming index with %d parallel workers", worker_count)
        payloads: list[tuple[str, list[str], str, float, float]] = []
        for name, image_paths in image_groups.items():
            sample = image_paths[0]
            name_folder = _name_folder_for_image(sample, root, skip_levels)
            payloads.append(
                (
                    name,
                    [str(path.resolve()) for path in image_paths],
                    str((name_folder or sample.parent).resolve()),
                    filt.min_det_score,
                    filt.min_area_ratio,
                )
            )
        completed = 0
        results: dict[str, tuple[Optional[list[float]], Optional[str], Optional[str], int, int]] = {}

        with ProcessPoolExecutor(
            max_workers=worker_count,
            initializer=init_scan_worker,
            initargs=(worker_count,),
        ) as pool:
            futures = [pool.submit(_index_student_worker, payload) for payload in payloads]
            for future in as_completed(futures):
                if should_cancel and should_cancel():
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                name, embedding, source_image, name_folder_str, skipped_no_face, skipped_multi_face = (
                    future.result()
                )
                results[name] = (
                    embedding,
                    source_image,
                    name_folder_str,
                    skipped_no_face,
                    skipped_multi_face,
                )
                index.skipped_no_face += skipped_no_face
                index.skipped_multi_face += skipped_multi_face
                completed += 1
                if on_progress:
                    on_progress(
                        "naming",
                        completed,
                        total,
                        f"Indexing reference: {name}",
                    )

        for name in image_groups:
            embedding, source_image, name_folder_str, _, _ = results.get(
                name, (None, None, None, 0, 0)
            )
            if embedding is None:
                index.skipped_empty_folders += 1
                logger.warning("No single-face reference photo for student name: %s", name)
                continue
            index.references.append(
                NamedReference(
                    name=name,
                    centroid=normalize_embedding(np.asarray(embedding, dtype=np.float64)),
                    sample_count=1,
                    source_image=Path(source_image) if source_image else None,
                    folder=Path(name_folder_str) if name_folder_str else root,
                )
            )
            logger.debug("Reference %s from %s", name, source_image)

    return index


def _index_student_worker(
    args: tuple[str, list[str], str, float, float],
) -> tuple[str, Optional[list[float]], Optional[str], Optional[str], int, int]:
    """Find the first single-face reference photo for one student name."""
    name, image_strs, name_folder_str, min_det_score, min_area_ratio = args
    face_filter = FaceFilterParams(min_det_score=min_det_score, min_area_ratio=min_area_ratio)
    image_paths = [Path(path) for path in image_strs]
    embedding, source_image, skipped_no_face, skipped_multi_face = _first_single_face_in_images(
        image_paths,
        face_filter=face_filter,
    )
    if embedding is None:
        return name, None, None, name_folder_str, skipped_no_face, skipped_multi_face
    return (
        name,
        embedding.astype(float).tolist(),
        str(source_image.resolve()) if source_image else None,
        name_folder_str,
        skipped_no_face,
        skipped_multi_face,
    )


def build_naming_index(
    root: Path,
    *,
    skip_levels: int = 0,
    workers: int | None = None,
    face_filter: FaceFilterParams | None = None,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> NamingIndex:
    """Scan naming_reference — bottom-up from photos; one single-face photo per name is enough."""
    from reference_cache import (
        compute_reference_fingerprint,
        load_reference_cache_payload,
        save_reference_cache_payload,
    )

    if not root.is_dir():
        raise ValueError(f"Naming reference folder does not exist: {root}")

    root = root.resolve()
    filt = face_filter or FaceFilterParams()
    warnings = duplicate_name_warnings(root, skip_levels)
    for message in warnings:
        logger.warning(message)

    fingerprint = compute_reference_fingerprint(root)
    cached_payload = load_reference_cache_payload(
        root,
        skip_levels,
        filt,
        fingerprint=fingerprint,
    )
    if cached_payload is not None:
        index = _index_from_cache_payload(cached_payload)
        index.duplicate_name_warnings = warnings
        if on_progress and index.references:
            on_progress(
                "naming",
                len(index.references),
                len(index.references),
                f"Using cached reference index ({len(index.references)} identities)",
            )
        return index

    index = _build_naming_index_fresh(
        root,
        skip_levels=skip_levels,
        workers=workers,
        filt=filt,
        on_progress=on_progress,
        should_cancel=should_cancel,
    )
    index.duplicate_name_warnings = warnings

    if not index.references:
        raise ValueError(
            f"No usable naming reference names under {root} (skip levels={skip_levels}). "
            "Expected student names by walking up from each photo's folder. "
            "Try adjusting Ref folder skip."
        )

    save_reference_cache_payload(
        root,
        skip_levels,
        filt,
        _index_to_cache_payload(index),
        fingerprint=fingerprint,
    )
    return index


def match_cluster_to_name(
    embeddings: list[np.ndarray],
    index: NamingIndex,
    tolerance: float = MATCH_TOLERANCE,
) -> tuple[Optional[str], float]:
    if not embeddings or not index.references:
        return None, -1.0

    cluster_centroid = _centroid(embeddings)
    best_name: Optional[str] = None
    best_similarity = -1.0

    for ref in index.references:
        similarity = cosine_similarity(cluster_centroid, ref.centroid)
        if similarity > best_similarity:
            best_similarity = similarity
            best_name = ref.name

    if best_name is not None and best_similarity >= tolerance:
        return best_name, best_similarity
    return None, best_similarity


def build_person_rename_map(
    cluster_embeddings: dict[ClusterKey, list[np.ndarray]],
    index: NamingIndex,
    tolerance: float = MATCH_TOLERANCE,
    *,
    on_progress: Optional[ProgressCallback] = None,
) -> dict[ClusterKey, str]:
    """Map (class, cluster_index) → reference folder name."""
    rename: dict[ClusterKey, str] = {}
    items = list(cluster_embeddings.items())
    total = len(items)
    for index_num, (key, embeddings) in enumerate(items, start=1):
        if on_progress and total:
            class_folder, cluster_index = key
            label = (
                f"{class_folder}/Person_{cluster_index + 1:03d}"
                if class_folder
                else f"Person_{cluster_index + 1:03d}"
            )
            on_progress(
                "naming_match",
                index_num,
                total,
                f"Matching cluster: {label}",
            )
        name, similarity = match_cluster_to_name(embeddings, index, tolerance)
        if name:
            rename[key] = name
            logger.info(
                "Named cluster %s → %s (similarity %.3f)",
                key,
                name,
                similarity,
            )
    return rename


def resolve_person_label(
    cluster_index: int,
    class_folder: Optional[str],
    rename_map: dict[ClusterKey, str],
    default_label: str,
) -> str:
    return rename_map.get((class_folder, cluster_index), default_label)

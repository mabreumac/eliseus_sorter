"""Optional naming_reference: match Person_XXX clusters to named folders."""

from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from config import MATCH_TOLERANCE
from embeddings import cosine_similarity, encode_faces_from_path, normalize_embedding
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
    if lowered in {"_unmatched", "_class_photos", "_group_photos", "group_photos"}:
        return False
    return True


def _first_single_face_in_folder(
    folder: Path,
    index: NamingIndex,
) -> tuple[Optional[np.ndarray], Optional[Path]]:
    """Use the first single-face photo found; skip the rest of the folder."""
    for image_path in iter_images_recursive(folder):
        encoded = encode_faces_from_path(image_path, GroupPhotoMode.FIRST_FACE)
        if encoded.error:
            continue
        if encoded.num_faces == 0:
            index.skipped_no_face += 1
            continue
        if encoded.num_faces > 1:
            index.skipped_multi_face += 1
            continue
        if encoded.faces:
            return encoded.faces[0].embedding, image_path
    return None, None


def _index_folder_worker(
    args: tuple[str, str],
) -> tuple[str, Optional[list[float]], Optional[str], int, int]:
    """Find the first single-face reference photo in one student folder."""
    name, folder_str = args
    folder = Path(folder_str)
    skipped_no_face = 0
    skipped_multi_face = 0
    for image_path in iter_images_recursive(folder):
        encoded = encode_faces_from_path(image_path, GroupPhotoMode.FIRST_FACE)
        if encoded.error:
            continue
        if encoded.num_faces == 0:
            skipped_no_face += 1
            continue
        if encoded.num_faces > 1:
            skipped_multi_face += 1
            continue
        if encoded.faces:
            embedding = encoded.faces[0].embedding.astype(float).tolist()
            return name, embedding, str(image_path.resolve()), skipped_no_face, skipped_multi_face
    return name, None, None, skipped_no_face, skipped_multi_face


def _iter_person_folders(root: Path, skip_levels: int) -> list[tuple[str, Path]]:
    """Return (student_name, folder) pairs, skipping wrapper folders under root."""
    if skip_levels < 0:
        raise ValueError("Naming reference skip levels must be 0 or greater.")

    if skip_levels == 0:
        return [
            (folder.name, folder)
            for folder in sorted(root.iterdir())
            if folder.is_dir() and _is_reference_folder(folder.name)
        ]

    frontier = [root]
    for _ in range(skip_levels):
        next_frontier: list[Path] = []
        for base in frontier:
            for child in sorted(base.iterdir()):
                if child.is_dir():
                    next_frontier.append(child)
        frontier = next_frontier

    folders: list[tuple[str, Path]] = []
    for base in frontier:
        for child in sorted(base.iterdir()):
            if child.is_dir() and _is_reference_folder(child.name):
                folders.append((child.name, child))
    return folders


def build_naming_index(
    root: Path,
    *,
    skip_levels: int = 0,
    workers: int | None = None,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> NamingIndex:
    """Scan naming_reference — one single-face photo per person folder is enough."""
    if not root.is_dir():
        raise ValueError(f"Naming reference folder does not exist: {root}")

    index = NamingIndex()
    person_folders = _iter_person_folders(root, skip_levels)
    total = len(person_folders)
    worker_count = effective_scan_workers(workers)

    if worker_count <= 1:
        for folder_index, (name, folder) in enumerate(person_folders, start=1):
            if should_cancel and should_cancel():
                break
            if on_progress:
                on_progress(
                    "naming",
                    folder_index,
                    total,
                    f"Indexing reference: {name}",
                )

            embedding, source_image = _first_single_face_in_folder(folder, index)
            if embedding is None:
                index.skipped_empty_folders += 1
                logger.warning("Naming reference folder has no single-face photos: %s", name)
                continue

            index.references.append(
                NamedReference(
                    name=name,
                    centroid=normalize_embedding(embedding),
                    sample_count=1,
                    source_image=source_image,
                    folder=folder,
                )
            )
            logger.debug("Reference %s from %s", name, source_image)
    else:
        logger.info("Naming index with %d parallel workers", worker_count)
        payloads = [(name, str(folder.resolve())) for name, folder in person_folders]
        folder_by_name = {name: folder for name, folder in person_folders}
        completed = 0
        results: dict[str, tuple[Optional[list[float]], Optional[str], int, int]] = {}

        with ProcessPoolExecutor(
            max_workers=worker_count,
            initializer=init_scan_worker,
            initargs=(worker_count,),
        ) as pool:
            futures = [pool.submit(_index_folder_worker, payload) for payload in payloads]
            for future in as_completed(futures):
                if should_cancel and should_cancel():
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                name, embedding, source_image, skipped_no_face, skipped_multi_face = future.result()
                results[name] = (embedding, source_image, skipped_no_face, skipped_multi_face)
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

        for name, folder in person_folders:
            embedding, source_image, _, _ = results.get(name, (None, None, 0, 0))
            if embedding is None:
                index.skipped_empty_folders += 1
                logger.warning("Naming reference folder has no single-face photos: %s", name)
                continue
            index.references.append(
                NamedReference(
                    name=name,
                    centroid=normalize_embedding(np.asarray(embedding, dtype=np.float64)),
                    sample_count=1,
                    source_image=Path(source_image) if source_image else None,
                    folder=folder_by_name[name],
                )
            )
            logger.debug("Reference %s from %s", name, source_image)

    if not index.references:
        raise ValueError(
            f"No usable naming reference folders under {root} "
            f"(skip levels={skip_levels}). "
            "Expected student-name folders after skipping the given number of wrapper folders."
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
            label = f"{class_folder}/Person_{cluster_index + 1:03d}" if class_folder else f"Person_{cluster_index + 1:03d}"
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

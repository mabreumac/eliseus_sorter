"""Assign person folder order (001, 002, …) by first appearance in input file order."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TypeAlias

ClusterKey: TypeAlias = tuple[str | None, int]


def image_path_order_index(image_paths: list[Path]) -> dict[str, int]:
    """Map resolved path string → position in the input pile (scan order)."""
    return {str(path.resolve()): index for index, path in enumerate(image_paths)}


def build_person_order(
    *,
    cluster_appearances: dict[ClusterKey, list[tuple[int, int]]],
) -> dict[ClusterKey, int]:
    """
    Assign 0-based person order indices within each class (all clusters).

    Each cluster is ordered by the earliest input index among its single-face
    photos (num_faces == 1). Clusters with no singles fall back to earliest
    photo of any kind.
    """
    by_class: dict[str | None, list[ClusterKey]] = defaultdict(list)
    for key in cluster_appearances:
        by_class[key[0]].append(key)

    reorder: dict[ClusterKey, int] = {}
    for class_keys in by_class.values():
        ordered = sorted(class_keys, key=lambda key: _cluster_sort_key(key, cluster_appearances))
        for new_index, key in enumerate(ordered):
            reorder[key] = new_index
    return reorder


def build_unnamed_person_order(
    *,
    rename_map: dict[ClusterKey, str],
    cluster_appearances: dict[ClusterKey, list[tuple[int, int]]],
) -> dict[ClusterKey, int]:
    """Backwards-compatible alias — order includes named and unnamed clusters."""
    del rename_map
    return build_person_order(cluster_appearances=cluster_appearances)


def _cluster_sort_key(
    key: ClusterKey,
    cluster_appearances: dict[ClusterKey, list[tuple[int, int]]],
) -> tuple[int, int, int]:
    hits = cluster_appearances.get(key, [])
    single_indices = [index for index, num_faces in hits if num_faces == 1]
    if single_indices:
        return (0, min(single_indices), key[1])
    any_indices = [index for index, _ in hits if index >= 0]
    if any_indices:
        return (1, min(any_indices), key[1])
    return (2, key[1], 0)


def collect_class_cluster_appearances(
    *,
    path_order: dict[str, int],
    per_image_faces: list[tuple[Path, list, object | None]],
    face_assignments: dict[tuple[str, int], tuple[str, int, float]],
) -> dict[ClusterKey, list[tuple[int, int]]]:
    """Gather (input_index, num_faces) for every face assignment in class sort."""
    appearances: dict[ClusterKey, list[tuple[int, int]]] = defaultdict(list)
    for image_path, faces, error in per_image_faces:
        if error or not faces:
            continue
        resolved = str(image_path.resolve())
        input_index = path_order.get(resolved, -1)
        num_faces = faces[0].num_faces
        for face in faces:
            assignment = face_assignments.get((resolved, face.face_index))
            if not assignment:
                continue
            class_folder, cluster_index, _ = assignment
            cluster_key: ClusterKey = (class_folder, cluster_index)
            appearances[cluster_key].append((input_index, num_faces))
    return dict(appearances)


def collect_flat_cluster_appearances(
    *,
    path_order: dict[str, int],
    per_image_faces: list[tuple[Path, list, object | None]],
    cluster_assignments: dict[tuple[str, int], tuple[int, float]],
) -> dict[ClusterKey, list[tuple[int, int]]]:
    """Gather (input_index, num_faces) for flat (no class) sort."""
    appearances: dict[ClusterKey, list[tuple[int, int]]] = defaultdict(list)
    for image_path, faces, error in per_image_faces:
        if error or not faces:
            continue
        resolved = str(image_path.resolve())
        input_index = path_order.get(resolved, -1)
        num_faces = faces[0].num_faces
        for face in faces:
            assignment = cluster_assignments.get((resolved, face.face_index))
            if not assignment:
                continue
            cluster_index, _ = assignment
            cluster_key: ClusterKey = (None, cluster_index)
            appearances[cluster_key].append((input_index, num_faces))
    return dict(appearances)

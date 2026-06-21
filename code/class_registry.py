"""Per-class face clustering for class-photo-driven sorting."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from clustering import FaceClusterer, person_id_label
from config import CLASS_FOLDER_PREFIX
from embeddings import cosine_similarity, normalize_embedding


def class_id_label(class_index: int) -> str:
    return f"{CLASS_FOLDER_PREFIX}{class_index + 1:03d}"


@dataclass
class ClassBucket:
    label: str
    clusterer: FaceClusterer
    class_photo_path: Path
    seed_assignments: dict[tuple[str, int], tuple[int, float]] = field(
        default_factory=dict
    )


class ClassRegistry:
    """One clusterer per class; classes are seeded from large group photos."""

    def __init__(self, similarity_threshold: float) -> None:
        self.similarity_threshold = similarity_threshold
        self.classes: list[ClassBucket] = []

    @property
    def num_classes(self) -> int:
        return len(self.classes)

    def add_class_from_photo(
        self,
        photo_path: Path,
        face_embeddings: list[tuple[int, np.ndarray]],
    ) -> str:
        label = class_id_label(len(self.classes))
        clusterer = FaceClusterer(similarity_threshold=self.similarity_threshold)
        bucket = ClassBucket(
            label=label,
            clusterer=clusterer,
            class_photo_path=photo_path,
        )
        resolved = str(photo_path.resolve())
        for face_index, embedding in face_embeddings:
            cluster_index = clusterer.add_cluster(embedding)
            bucket.seed_assignments[(resolved, face_index)] = (cluster_index, 1.0)
        self.classes.append(bucket)
        return label

    def assign_face(
        self, embedding: np.ndarray
    ) -> tuple[str | None, int | None, float]:
        """Pick the best (class, person cluster) match across all classes."""
        embedding = normalize_embedding(embedding)
        best_class: ClassBucket | None = None
        best_cluster = -1
        best_similarity = -1.0

        for bucket in self.classes:
            cluster_index, similarity = bucket.clusterer.find_best_cluster(embedding)
            if cluster_index < 0:
                continue
            if similarity > best_similarity:
                best_similarity = similarity
                best_class = bucket
                best_cluster = cluster_index

        if best_class is None or best_similarity < self.similarity_threshold:
            return None, None, best_similarity

        best_class.clusterer.assign_to_cluster(best_cluster, embedding)
        return best_class.label, best_cluster, best_similarity

    def lookup_seed(
        self, image_path: Path, face_index: int
    ) -> tuple[str | None, int | None, float]:
        key = (str(image_path.resolve()), face_index)
        for bucket in self.classes:
            hit = bucket.seed_assignments.get(key)
            if hit is not None:
                return bucket.label, hit[0], hit[1]
        return None, None, -1.0

    def class_for_photo(self, photo_path: Path) -> str | None:
        resolved = str(photo_path.resolve())
        for bucket in self.classes:
            if str(bucket.class_photo_path.resolve()) == resolved:
                return bucket.label
        return None

"""Per-class face clustering for class-photo-driven sorting."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from clustering import FaceClusterer, person_id_label
from config import CLASS_FOLDER_PREFIX, CLASS_PHOTO_MERGE_RATIO
from embeddings import normalize_embedding

logger = logging.getLogger(__name__)


def class_id_label(class_index: int) -> str:
    return f"{CLASS_FOLDER_PREFIX}{class_index + 1:03d}"


@dataclass
class ClassBucket:
    label: str
    clusterer: FaceClusterer
    class_photo_paths: list[Path] = field(default_factory=list)
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

    def register_class_photo(
        self,
        photo_path: Path,
        face_embeddings: list[tuple[int, np.ndarray]],
    ) -> str:
        """Add a class photo or merge it into an existing class if faces overlap."""
        if not face_embeddings:
            return self.add_class_from_photo(photo_path, face_embeddings)

        embeddings_only = [embedding for _, embedding in face_embeddings]
        best_bucket: ClassBucket | None = None
        best_ratio = 0.0

        for bucket in self.classes:
            ratio = self._match_ratio(embeddings_only, bucket)
            if ratio > best_ratio:
                best_ratio = ratio
                best_bucket = bucket

        if (
            best_bucket is not None
            and best_ratio >= CLASS_PHOTO_MERGE_RATIO
        ):
            logger.info(
                "Merging class photo %s into %s (%.0f%% faces matched)",
                photo_path.name,
                best_bucket.label,
                best_ratio * 100,
            )
            self.merge_class_photo(best_bucket, photo_path, face_embeddings)
            return best_bucket.label

        return self.add_class_from_photo(photo_path, face_embeddings)

    def _match_ratio(
        self,
        embeddings: list[np.ndarray],
        bucket: ClassBucket,
    ) -> float:
        if not embeddings or not bucket.clusterer.num_clusters:
            return 0.0
        matched = 0
        for embedding in embeddings:
            cluster_index, similarity = bucket.clusterer.find_best_cluster(embedding)
            if cluster_index >= 0 and similarity >= self.similarity_threshold:
                matched += 1
        return matched / len(embeddings)

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
            class_photo_paths=[photo_path],
        )
        resolved = str(photo_path.resolve())
        for face_index, embedding in face_embeddings:
            cluster_index = clusterer.add_cluster(embedding)
            bucket.seed_assignments[(resolved, face_index)] = (cluster_index, 1.0)
        self.classes.append(bucket)
        logger.info("New class %s from %s", label, photo_path.name)
        return label

    def merge_class_photo(
        self,
        bucket: ClassBucket,
        photo_path: Path,
        face_embeddings: list[tuple[int, np.ndarray]],
    ) -> None:
        bucket.class_photo_paths.append(photo_path)
        resolved = str(photo_path.resolve())
        for face_index, embedding in face_embeddings:
            cluster_index, similarity = bucket.clusterer.find_best_cluster(embedding)
            if cluster_index >= 0 and similarity >= self.similarity_threshold:
                bucket.clusterer.assign_to_cluster(cluster_index, embedding)
            else:
                cluster_index = bucket.clusterer.add_cluster(embedding)
                similarity = 1.0
            bucket.seed_assignments[(resolved, face_index)] = (
                cluster_index,
                similarity,
            )

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
            if any(str(path.resolve()) == resolved for path in bucket.class_photo_paths):
                return bucket.label
            if any(key[0] == resolved for key in bucket.seed_assignments):
                return bucket.label
        return None

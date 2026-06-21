"""Unsupervised face clustering into generic person IDs (ArcFace cosine similarity)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from embeddings import cosine_similarity, normalize_embedding


def person_id_label(cluster_index: int) -> str:
    return f"Person_{cluster_index + 1:03d}"


@dataclass
class FaceClusterer:
    """
    Online centroid clustering on L2-normalized ArcFace embeddings.

    ``similarity_threshold``: minimum cosine similarity to join a cluster
    (InsightFace typical same-person values ≈ 0.4–0.7+).
    """

    similarity_threshold: float
    _centroids: list[np.ndarray] = field(default_factory=list)
    _counts: list[int] = field(default_factory=list)

    @property
    def num_clusters(self) -> int:
        return len(self._centroids)

    def assign(self, embedding: np.ndarray) -> tuple[int, float]:
        """Return (cluster_index, cosine similarity to assigned centroid)."""
        embedding = normalize_embedding(embedding)
        if not self._centroids:
            self._add_cluster(embedding)
            return 0, 1.0

        best_index, best_similarity = self.find_best_cluster(embedding)

        if best_similarity >= self.similarity_threshold:
            self._update_centroid(best_index, embedding)
            return best_index, best_similarity

        new_index = self._add_cluster(embedding)
        return new_index, 1.0

    def find_best_cluster(self, embedding: np.ndarray) -> tuple[int, float]:
        embedding = normalize_embedding(embedding)
        if not self._centroids:
            return -1, -1.0
        similarities = [
            cosine_similarity(embedding, centroid) for centroid in self._centroids
        ]
        best_index = int(np.argmax(similarities))
        return best_index, similarities[best_index]

    def assign_to_cluster(self, cluster_index: int, embedding: np.ndarray) -> None:
        self._update_centroid(cluster_index, normalize_embedding(embedding))

    def add_cluster(self, embedding: np.ndarray) -> int:
        """Always create a new cluster (used when seeding a class photo)."""
        return self._add_cluster(normalize_embedding(embedding))

    def assign_batch(self, embeddings: list[np.ndarray]) -> list[tuple[int, float]]:
        return [self.assign(embedding) for embedding in embeddings]

    def _add_cluster(self, embedding: np.ndarray) -> int:
        self._centroids.append(normalize_embedding(embedding))
        self._counts.append(1)
        return len(self._centroids) - 1

    def _update_centroid(self, index: int, embedding: np.ndarray) -> None:
        count = self._counts[index]
        updated = (
            self._centroids[index] * count + normalize_embedding(embedding)
        ) / (count + 1)
        self._centroids[index] = normalize_embedding(updated)
        self._counts[index] = count + 1

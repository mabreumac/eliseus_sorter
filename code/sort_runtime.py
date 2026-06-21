"""Sort pipeline timing metrics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SortRuntime:
    scan_seconds: float = 0.0
    cluster_seconds: float = 0.0
    copy_seconds: float = 0.0
    num_images: int = 0
    num_faces_detected: int = 0
    num_images_with_face: int = 0
    num_images_no_face: int = 0

    @property
    def total_seconds(self) -> float:
        return self.scan_seconds + self.cluster_seconds + self.copy_seconds

"""Group photo handling modes and settings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from config import GROUP_PHOTOS_DIR, OUTPUT_DIR, SORTED_STUDENTS_DIR


class GroupPhotoMode(str, Enum):
    """How to handle images with more than one detected face."""

    FIRST_FACE = "first_face"
    LARGEST_FACE = "largest_face"
    ALL_FACES = "all_faces"
    SKIP = "skip"


GROUP_PHOTO_MODE_LABELS: dict[GroupPhotoMode, str] = {
    GroupPhotoMode.FIRST_FACE: "First face only",
    GroupPhotoMode.LARGEST_FACE: "Largest face only",
    GroupPhotoMode.ALL_FACES: "All faces (one match per person)",
    GroupPhotoMode.SKIP: "Skip group photos (2+ faces)",
}


@dataclass(frozen=True)
class GroupPhotoSettings:
    """User-configurable group photo behaviour."""

    mode: GroupPhotoMode = GroupPhotoMode.FIRST_FACE
    group_photos_dir: Optional[Path] = None
    sort_to_student_folders: bool = False
    sorted_output_dir: Path = SORTED_STUDENTS_DIR

    def resolved_group_photos_dir(self) -> Optional[Path]:
        if self.group_photos_dir is None:
            return None
        path = self.group_photos_dir
        if not str(path).strip():
            return None
        return path

    def resolved_sorted_output_dir(self, output_dir: Path = OUTPUT_DIR) -> Path:
        if self.sort_to_student_folders:
            return self.sorted_output_dir
        return output_dir / "sorted_students"

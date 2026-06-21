"""Group photo handling modes and settings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from config import GROUP_OUTPUT_FOLDER


class GroupPhotoMode(str, Enum):
    """How to handle images with more than one detected face."""

    FIRST_FACE = "first_face"
    LARGEST_FACE = "largest_face"
    ALL_FACES = "all_faces"
    SKIP = "skip"


GROUP_PHOTO_MODE_LABELS: dict[GroupPhotoMode, str] = {
    GroupPhotoMode.FIRST_FACE: "Group folder only",
    GroupPhotoMode.LARGEST_FACE: "Group folder only (legacy)",
    GroupPhotoMode.ALL_FACES: "Group folder + person folders (all faces)",
    GroupPhotoMode.SKIP: "Group folder only, skip person folders",
}


def is_group_reference_folder(name: str, group_folder: str = GROUP_OUTPUT_FOLDER) -> bool:
    """True if a ground-truth folder holds group photos, not student reference."""
    normalized = name.strip().casefold()
    accepted = {
        group_folder.strip().casefold(),
        "grupo",
        "group_photos",  # legacy output / benchmark folder names
    }
    return normalized in accepted


@dataclass(frozen=True)
class GroupPhotoSettings:
    mode: GroupPhotoMode = GroupPhotoMode.FIRST_FACE
    group_output_folder: Optional[str] = GROUP_OUTPUT_FOLDER
    group_photos_dir: Optional[Path] = None
    sort_to_student_folders: bool = False
    sorted_output_dir: Optional[Path] = None

    def resolved_group_output_folder(self) -> Optional[str]:
        if self.group_output_folder is None:
            return None
        name = str(self.group_output_folder).strip()
        return name or None

    def resolved_group_photos_dir(self) -> Optional[Path]:
        if self.group_photos_dir is None:
            return None
        path = self.group_photos_dir
        if not str(path).strip():
            return None
        return path

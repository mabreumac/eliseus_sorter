"""Image loading and directory iteration utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import numpy as np
from PIL import Image

from config import (
    CLASS_FOLDER_PREFIX,
    CLASS_PHOTOS_FOLDER,
    GROUP_OUTPUT_FOLDER,
    IMAGE_EXTENSIONS,
    MAX_IMAGE_WIDTH,
    UNMATCHED_FOLDER,
)
from group_photos import is_group_reference_folder


def is_sort_output_segment(name: str) -> bool:
    """True if a top-level folder name is produced by the sorter (skip when re-scanning in place)."""
    if name in (UNMATCHED_FOLDER, CLASS_PHOTOS_FOLDER, GROUP_OUTPUT_FOLDER):
        return True
    if name.startswith(CLASS_FOLDER_PREFIX):
        return True
    if name.startswith("Person_"):
        return True
    if name.startswith("run_"):
        return True
    return False


def _skip_in_place_input(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    if not rel.parts:
        return False
    return is_sort_output_segment(rel.parts[0])


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def iter_image_files(directory: Path) -> Generator[Path, None, None]:
    if not directory.is_dir():
        return
    for path in sorted(directory.iterdir()):
        if is_image_file(path):
            yield path


def iter_ground_truth_images(
    ground_truth_dir: Path,
    *,
    include_group_folder: bool = False,
) -> Generator[tuple[str, Path], None, None]:
    if not ground_truth_dir.is_dir():
        return
    for student_dir in sorted(ground_truth_dir.iterdir()):
        if not student_dir.is_dir():
            continue
        if not include_group_folder and is_group_reference_folder(student_dir.name):
            continue
        for image_path in iter_image_files(student_dir):
            yield student_dir.name, image_path


def ground_truth_labels(
    ground_truth_dir: Path,
    *,
    include_group_folder: bool = True,
) -> dict[str, str]:
    """Map image filename → ground-truth folder name (student or _group_photos)."""
    labels: dict[str, str] = {}
    for student, image_path in iter_ground_truth_images(
        ground_truth_dir, include_group_folder=include_group_folder
    ):
        name = image_path.name
        if name in labels and labels[name] != student:
            raise ValueError(
                f"Duplicate filename {name!r} in {labels[name]!r} and {student!r}"
            )
        labels[name] = student
    return labels


def iter_test_subset_images(directory: Path) -> Generator[Path, None, None]:
    yield from iter_image_files(directory)


def iter_images_recursive(directory: Path) -> Generator[Path, None, None]:
    """All images under directory (any depth), sorted by path."""
    yield from iter_sort_input_images(directory, recursive=True, in_place=False)


def iter_sort_input_images(
    directory: Path,
    *,
    recursive: bool = True,
    in_place: bool = False,
) -> Generator[Path, None, None]:
    """Images to scan for sorting; skips existing sort output folders when in_place."""
    if not directory.is_dir():
        return
    if recursive:
        for path in sorted(directory.rglob("*")):
            if not is_image_file(path):
                continue
            if in_place and _skip_in_place_input(path, directory):
                continue
            yield path
    else:
        for path in iter_image_files(directory):
            if in_place and _skip_in_place_input(path, directory):
                continue
            yield path


def iter_match_sources(
    input_dir: Path,
    group_photos_dir: Path | None = None,
) -> Generator[tuple[str, Path], None, None]:
    for image_path in iter_test_subset_images(input_dir):
        yield "input", image_path
    if group_photos_dir is not None and group_photos_dir.is_dir():
        for image_path in iter_image_files(group_photos_dir):
            yield "group_photos", image_path


def count_ground_truth_images(ground_truth_dir: Path) -> int:
    return sum(1 for _ in iter_ground_truth_images(ground_truth_dir))


def count_test_subset_images(directory: Path) -> int:
    return sum(1 for _ in iter_test_subset_images(directory))


def count_match_sources(input_dir: Path, group_photos_dir: Path | None = None) -> int:
    return sum(1 for _ in iter_match_sources(input_dir, group_photos_dir))


def load_image_resized(image_path: Path, max_width: int = MAX_IMAGE_WIDTH) -> np.ndarray:
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        width, height = img.size
        if width > max_width:
            new_height = int(height * max_width / width)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
        return np.asarray(img, dtype=np.uint8)

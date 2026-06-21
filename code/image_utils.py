"""Image loading and directory iteration utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import numpy as np
from PIL import Image

from config import IMAGE_EXTENSIONS, MAX_IMAGE_WIDTH
from group_photos import is_group_reference_folder


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
    """Map image filename → ground-truth folder name (student or Grupo)."""
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

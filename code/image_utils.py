"""Image loading and directory iteration utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import numpy as np
from PIL import Image

from config import GROUND_TRUTH_DIR, IMAGE_EXTENSIONS, MAX_IMAGE_WIDTH, TEST_SUBSET_DIR


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def iter_image_files(directory: Path) -> Generator[Path, None, None]:
    """Yield image paths under directory (non-recursive)."""
    if not directory.is_dir():
        return
    for path in sorted(directory.iterdir()):
        if is_image_file(path):
            yield path


def iter_ground_truth_images(
    ground_truth_dir: Path = GROUND_TRUTH_DIR,
) -> Generator[tuple[str, Path], None, None]:
    """
    Yield (student_name, image_path) for ground-truth layout:
    ground_truth/student_name/image.jpg
    """
    if not ground_truth_dir.is_dir():
        return

    for student_dir in sorted(ground_truth_dir.iterdir()):
        if not student_dir.is_dir():
            continue
        student_name = student_dir.name
        for image_path in iter_image_files(student_dir):
            yield student_name, image_path


def iter_test_subset_images(
    test_subset_dir: Path = TEST_SUBSET_DIR,
) -> Generator[Path, None, None]:
    """Yield loose unassigned images from test_subset/."""
    yield from iter_image_files(test_subset_dir)


def count_ground_truth_images(ground_truth_dir: Path = GROUND_TRUTH_DIR) -> int:
    """Count indexable ground-truth images (for progress bars)."""
    return sum(1 for _ in iter_ground_truth_images(ground_truth_dir))


def count_test_subset_images(test_subset_dir: Path = TEST_SUBSET_DIR) -> int:
    """Count test-subset images (for progress bars)."""
    return sum(1 for _ in iter_test_subset_images(test_subset_dir))


def load_image_resized(
    image_path: Path,
    max_width: int = MAX_IMAGE_WIDTH,
) -> np.ndarray:
    """
    Load an image as RGB uint8 numpy array, downscaled in-memory.

    Raises
    ------
    UnidentifiedImageError
        If the file is not a valid image.
    OSError
        If the file cannot be read.
    """
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        width, height = img.size
        if width > max_width:
            new_height = int(height * max_width / width)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
        return np.asarray(img, dtype=np.uint8)

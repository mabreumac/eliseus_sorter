"""Image loading and directory iteration utilities."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Generator

import cv2
import numpy as np
from PIL import Image

from config import (
    CLASS_FOLDER_PREFIX,
    CLASS_PHOTOS_FOLDER,
    GROUP_OUTPUT_FOLDER,
    IMAGE_EXTENSIONS,
    MAX_IMAGE_WIDTH,
    NO_CLASS_FOLDER,
    SORT_RUN_FOLDER_SUFFIX,
    UNMATCHED_FOLDER,
)
from group_photos import is_group_reference_folder

# Sorter output person folders: 001, 002, 001_Maria (legacy: Person_001)
PERSON_OUTPUT_FOLDER = re.compile(r"^\d{3}(_.*)?$")


def is_person_output_folder(name: str) -> bool:
    return bool(PERSON_OUTPUT_FOLDER.match(name)) or name.startswith("Person_")


def is_sort_output_segment(name: str) -> bool:
    """True if a top-level folder name is produced by the sorter (skip when re-scanning in place)."""
    if name in (UNMATCHED_FOLDER, NO_CLASS_FOLDER, CLASS_PHOTOS_FOLDER, GROUP_OUTPUT_FOLDER):
        return True
    if name.startswith(CLASS_FOLDER_PREFIX):
        return True
    if is_person_output_folder(name):
        return True
    if name.startswith("run_"):
        return True
    if name.endswith(SORT_RUN_FOLDER_SUFFIX):
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


def _is_junk_image_path(path: Path) -> bool:
    """macOS AppleDouble (._*) and metadata paths on FAT/exFAT external drives."""
    name = path.name
    if name.startswith("._"):
        return True
    if name == ".DS_Store":
        return True
    return "__MACOSX" in path.parts


def is_image_file(path: Path) -> bool:
    if _is_junk_image_path(path):
        return False
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
    yield from iter_sort_input_images(directory, recursive=True, skip_sort_outputs=False)


def iter_sort_input_images(
    directory: Path,
    *,
    recursive: bool = True,
    skip_sort_outputs: bool = False,
) -> Generator[Path, None, None]:
    """Images to scan for sorting; skips existing sort output folders when requested."""
    if not directory.is_dir():
        return
    if recursive:
        for path in sorted(directory.rglob("*")):
            if not is_image_file(path):
                continue
            if skip_sort_outputs and _skip_in_place_input(path, directory):
                continue
            yield path
    else:
        for path in iter_image_files(directory):
            if skip_sort_outputs and _skip_in_place_input(path, directory):
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


def load_image_bgr(image_path: Path) -> np.ndarray | None:
    """BGR uint8 array for OpenCV/InsightFace; handles Unicode paths and odd JPEG encodings."""
    path = Path(image_path)
    try:
        with path.open("rb") as handle:
            raw = np.frombuffer(handle.read(), dtype=np.uint8)
        if raw.size > 0:
            image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
            if image is not None:
                return image
    except OSError:
        pass

    try:
        with Image.open(path) as img:
            rgb = np.asarray(img.convert("RGB"), dtype=np.uint8)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except OSError:
        return None


def describe_image_read_probe(image_path: Path) -> str:
    """One-line diagnosis when face encoding cannot open a reference photo."""
    path = Path(image_path)
    try:
        size = path.stat().st_size
    except OSError as exc:
        return f"{path.name}: cannot access ({exc})"
    if size == 0:
        return f"{path.name}: file is empty (0 bytes)"
    try:
        with path.open("rb") as handle:
            header = handle.read(12)
    except OSError as exc:
        return f"{path.name}: {size} bytes but cannot open ({exc})"
    if load_image_bgr(path) is not None:
        return f"{path.name}: readable ({size} bytes)"
    tag = header[:4]
    return (
        f"{path.name}: {size} bytes, opens but cannot decode as an image "
        f"(header {tag!r})"
    )


def load_image_resized(image_path: Path, max_width: int = MAX_IMAGE_WIDTH) -> np.ndarray:
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        width, height = img.size
        if width > max_width:
            new_height = int(height * max_width / width)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
        return np.asarray(img, dtype=np.uint8)

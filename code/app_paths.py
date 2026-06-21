"""Resolve project and data paths for development vs macOS .app bundle."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_app_bundle() -> bool:
    return os.environ.get("ELISEUS_SORTER_APP") == "1"


def project_root() -> Path:
    if is_app_bundle():
        return Path(os.environ["ELISEUS_RESOURCES"])
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    if is_app_bundle():
        return Path.home() / "Library/Application Support/Eliseus Sorter/data"
    return project_root() / "data"


def support_dir() -> Path:
    return Path.home() / "Library/Application Support/Eliseus Sorter"


def ensure_data_dirs() -> None:
    for path in (
        data_dir(),
        data_dir() / "ground_truth",
        data_dir() / "test_subset",
        data_dir() / "group_photos",
        data_dir() / "output",
        data_dir() / "sorted_students",
    ):
        path.mkdir(parents=True, exist_ok=True)
    if is_app_bundle():
        support_dir().mkdir(parents=True, exist_ok=True)


# Exported constants (used by config.py)
PROJECT_ROOT = project_root()
DATA_DIR = data_dir()
GROUND_TRUTH_DIR = DATA_DIR / "ground_truth"
TEST_SUBSET_DIR = DATA_DIR / "test_subset"
GROUP_PHOTOS_DIR = DATA_DIR / "group_photos"
OUTPUT_DIR = DATA_DIR / "output"
SORTED_STUDENTS_DIR = OUTPUT_DIR / "sorted_students"
DATABASE_PATH = DATA_DIR / "school_photos.db"

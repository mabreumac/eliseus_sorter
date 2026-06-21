"""Central configuration for Eliseus Sorter."""

from app_paths import (  # noqa: F401 — re-export path constants
    DATA_DIR,
    DATABASE_PATH,
    GROUND_TRUTH_DIR,
    GROUP_PHOTOS_DIR,
    OUTPUT_DIR,
    PROJECT_ROOT,
    SORTED_STUDENTS_DIR,
    TEST_SUBSET_DIR,
    ensure_data_dirs,
    is_app_bundle,
)

# Face matching
MATCH_TOLERANCE = 0.6  # Euclidean distance; lower = stricter
MAX_IMAGE_WIDTH = 1024  # Downscale before detection/encoding

# Supported image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

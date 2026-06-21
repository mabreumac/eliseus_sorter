"""Central configuration for Eliseus Sorter."""

from pathlib import Path

# Project roots (data/ lives beside code/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
GROUND_TRUTH_DIR = DATA_DIR / "ground_truth"
TEST_SUBSET_DIR = DATA_DIR / "test_subset"
OUTPUT_DIR = DATA_DIR / "output"

# SQLite cache
DATABASE_PATH = DATA_DIR / "school_photos.db"

# Face matching
MATCH_TOLERANCE = 0.6  # Euclidean distance; lower = stricter
MAX_IMAGE_WIDTH = 1024  # Downscale before detection/encoding

# Supported image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

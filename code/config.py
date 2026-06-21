"""Central configuration for Eliseus Sorter."""

from app_paths import default_reference_db

# Face clustering — minimum cosine similarity to treat two faces as same person.
# InsightFace ArcFace: same person often ≥ 0.4; different people usually lower.
MATCH_TOLERANCE = 0.4
MAX_IMAGE_WIDTH = 1024

# InsightFace
INSIGHTFACE_MODEL = "buffalo_l"
INSIGHTFACE_DET_SIZE = (640, 640)
EMBEDDING_DIM = 512

# Production sorting
UNMATCHED_FOLDER = "_unmatched"
SORT_LOG_NAME = "_sort_log.csv"
CLASS_FOLDER_PREFIX = "class_"
CLASS_PHOTOS_FOLDER = "_class_photos"

# Group photos (multi-face, below class threshold) → per-class _group_photos folder
GROUP_OUTPUT_FOLDER = "_group_photos"

# Photos with more than this many faces define a class (e.g. 5 → 6+ faces = class photo)
DEFAULT_MIN_CLASS_FACES = 5

# Extra folder levels between naming_reference root and student-name folders (0 = direct children)
DEFAULT_NAMING_REFERENCE_SKIP = 0

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

# Legacy path for optional reference-DB tools (not used by cluster sort)
DEFAULT_REFERENCE_DB = default_reference_db()

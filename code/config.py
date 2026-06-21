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

# Group photos (multi-face) are copied here — not matched to individual students.
GROUP_OUTPUT_FOLDER = "Grupo"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

# Legacy path for optional reference-DB tools (not used by cluster sort)
DEFAULT_REFERENCE_DB = default_reference_db()

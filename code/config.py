"""Central configuration for Eliseus Sorter."""

from app_paths import default_reference_db

# Face clustering — minimum cosine similarity to treat two faces as same person.
# InsightFace ArcFace: same person often ≥ 0.4; different people usually lower.
MATCH_TOLERANCE = 0.4

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

# Min fraction of faces in a new class photo that must match an existing class to merge
# (same class photographed multiple times → one class_001 folder).
CLASS_PHOTO_MERGE_RATIO = 0.5

# Inference backend: auto (GPU if available), cpu, coreml (Apple), cuda (NVIDIA)
INFERENCE_DEVICE = "auto"
DEFAULT_INFERENCE_DEVICE = "auto"
ENV_INFERENCE_DEVICE = "ELISEUS_INFERENCE_DEVICE"

# ONNX Runtime CPU threads for face detection (0 = auto from core count, capped at 8)
ONNX_INTRA_OP_THREADS = 0

# Parallel scan processes: 0 or 1 = one image at a time (safest, least RAM)
# 2 = good speedup on 16GB Macs; 3–4 = faster but ~200MB RAM per worker
SCAN_WORKERS = 0
DEFAULT_SCAN_WORKERS = 1

# Resize large photos before detection (lower = faster, less accurate on tiny faces)
MAX_IMAGE_WIDTH = 1024

# Extra folder levels between naming_reference root and student-name folders (0 = direct children)
DEFAULT_NAMING_REFERENCE_SKIP = 0

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

# Legacy path for optional reference-DB tools (not used by cluster sort)
DEFAULT_REFERENCE_DB = default_reference_db()

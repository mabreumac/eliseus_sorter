"""InsightFace model singleton (buffalo_l — detection + ArcFace embeddings)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from config import INSIGHTFACE_DET_SIZE, INSIGHTFACE_MODEL


@lru_cache(maxsize=1)
def get_face_analysis() -> Any:
    from insightface.app import FaceAnalysis

    app = FaceAnalysis(name=INSIGHTFACE_MODEL, providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=INSIGHTFACE_DET_SIZE)
    return app

"""Disk cache for naming-reference embeddings (invalidated by folder fingerprint)."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app_paths import app_support_dir
from embeddings import FaceFilterParams
from image_utils import iter_images_recursive

logger = logging.getLogger(__name__)

CACHE_VERSION = 1
CACHE_DIR_NAME = "reference_cache"


def reference_cache_dir() -> Path:
    return app_support_dir() / CACHE_DIR_NAME


def _cache_file_path(root: Path, skip_levels: int, face_filter: FaceFilterParams) -> Path:
    root_key = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    filter_key = hashlib.sha256(
        f"{skip_levels}|{face_filter.min_det_score:.6f}|{face_filter.min_area_ratio:.6f}".encode()
    ).hexdigest()[:12]
    return reference_cache_dir() / f"{root_key}_{filter_key}.json"


def compute_reference_fingerprint(root: Path) -> str:
    """Hash relative paths + mtime + size for every image under root."""
    root = root.resolve()
    digest = hashlib.sha256()
    for path in sorted(iter_images_recursive(root), key=lambda p: str(p)):
        rel = path.relative_to(root).as_posix()
        stat = path.stat()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def save_reference_cache_payload(
    root: Path,
    skip_levels: int,
    face_filter: FaceFilterParams,
    payload: dict[str, Any],
    *,
    fingerprint: str,
) -> Path:
    reference_cache_dir().mkdir(parents=True, exist_ok=True)
    path = _cache_file_path(root, skip_levels, face_filter)
    body = {
        "version": CACHE_VERSION,
        "root": str(root.resolve()),
        "skip_levels": skip_levels,
        "face_filter": {
            "min_det_score": face_filter.min_det_score,
            "min_area_ratio": face_filter.min_area_ratio,
        },
        "fingerprint": fingerprint,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    logger.info(
        "Saved naming reference cache (%d identities): %s",
        len(payload.get("references") or []),
        path,
    )
    return path


def load_reference_cache_payload(
    root: Path,
    skip_levels: int,
    face_filter: FaceFilterParams,
    *,
    fingerprint: str,
) -> dict[str, Any] | None:
    path = _cache_file_path(root, skip_levels, face_filter)
    if not path.is_file():
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read naming reference cache: %s", exc)
        return None

    if body.get("version") != CACHE_VERSION:
        return None
    if body.get("fingerprint") != fingerprint:
        return None
    if body.get("skip_levels") != skip_levels:
        return None
    if str(root.resolve()) != body.get("root"):
        return None

    stored_filter = body.get("face_filter") or {}
    if not isinstance(stored_filter, dict):
        return None
    if abs(float(stored_filter.get("min_det_score", -1)) - face_filter.min_det_score) > 1e-9:
        return None
    if abs(float(stored_filter.get("min_area_ratio", -1)) - face_filter.min_area_ratio) > 1e-9:
        return None

    references = body.get("references") or []
    if not references:
        return None

    logger.info(
        "Loaded naming reference from cache (%d identities, built %s)",
        len(references),
        body.get("built_at_utc", "?"),
    )
    return body

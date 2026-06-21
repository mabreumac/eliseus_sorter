"""Parallel or sequential face scanning over input images."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from config import SCAN_WORKERS
from embeddings import encode_faces_from_path
from group_photos import GroupPhotoMode

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int, str], None]
CancelCallback = Callable[[], bool]


def effective_scan_workers(requested: int | None = None) -> int:
    """Return process count for scanning (1 = sequential). Capped for safety."""
    workers = SCAN_WORKERS if requested is None else requested
    if workers <= 1:
        return 1
    cpu = os.cpu_count() or 4
    return max(1, min(workers, 4, cpu))


def init_scan_worker(worker_count: int) -> None:
    from face_engine import configure_cpu_threads, get_face_analysis

    configure_cpu_threads(worker_count)
    get_face_analysis()


_init_scan_worker = init_scan_worker  # backwards compatible


def _scan_image_worker(args: tuple[str, str]) -> tuple[str, list[tuple[int, int, list[float]]], Optional[str]]:
    path_str, mode_value = args
    encoding = encode_faces_from_path(Path(path_str), GroupPhotoMode(mode_value))
    if encoding.error:
        return path_str, [], encoding.error
    faces = [
        (face.face_index, encoding.num_faces, face.embedding.astype(float).tolist())
        for face in encoding.faces
    ]
    return path_str, faces, None


def scan_all_images(
    image_paths: list[Path],
    encoding_mode: GroupPhotoMode,
    *,
    workers: int | None = None,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> list[tuple[Path, list[tuple[int, int, np.ndarray]], Optional[str]]]:
    """
    Detect faces in every image. Returns (path, [(face_index, num_faces, embedding)], error).
    Uses multiple processes only when SCAN_WORKERS > 0 (each process loads its own model).
    """
    total = len(image_paths)
    if total == 0:
        return []

    worker_count = effective_scan_workers(workers)
    mode_value = encoding_mode.value

    if worker_count <= 1:
        results: list[tuple[Path, list[tuple[int, int, np.ndarray]], Optional[str]]] = []
        for index, image_path in enumerate(image_paths, start=1):
            if should_cancel and should_cancel():
                break
            if on_progress:
                on_progress("scan", index, total, f"Scanning faces: {image_path.name}")
            encoding = encode_faces_from_path(image_path, encoding_mode)
            if encoding.error:
                results.append((image_path, [], encoding.error))
                continue
            faces = [
                (face.face_index, encoding.num_faces, face.embedding)
                for face in encoding.faces
            ]
            results.append((image_path, faces, None))
        return results

    logger.info("Scanning with %d parallel workers", worker_count)
    indexed = {str(path.resolve()): path for path in image_paths}
    payloads = [(str(path.resolve()), mode_value) for path in image_paths]
    raw: dict[str, tuple[list[tuple[int, int, list[float]]], Optional[str]]] = {}
    completed = 0

    with ProcessPoolExecutor(
        max_workers=worker_count,
        initializer=init_scan_worker,
        initargs=(worker_count,),
    ) as pool:
        futures = [pool.submit(_scan_image_worker, payload) for payload in payloads]
        for future in as_completed(futures):
            if should_cancel and should_cancel():
                pool.shutdown(wait=False, cancel_futures=True)
                break
            path_str, face_rows, error = future.result()
            raw[path_str] = (face_rows, error)
            completed += 1
            if on_progress:
                name = indexed[path_str].name if path_str in indexed else Path(path_str).name
                on_progress("scan", completed, total, f"Scanning faces: {name}")

    results = []
    for path in image_paths:
        key = str(path.resolve())
        face_rows, error = raw.get(key, ([], "scan did not complete"))
        faces = [
            (face_index, num_faces, np.asarray(embedding, dtype=np.float64))
            for face_index, num_faces, embedding in face_rows
        ]
        results.append((path, faces, error))
    return results

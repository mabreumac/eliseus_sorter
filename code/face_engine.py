"""InsightFace model singleton (buffalo_l — detection + ArcFace embeddings)."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

from config import (
    ENV_INFERENCE_DEVICE,
    INFERENCE_DEVICE,
    INSIGHTFACE_DET_SIZE,
    INSIGHTFACE_MODEL,
    ONNX_INTRA_OP_THREADS,
)

logger = logging.getLogger(__name__)

VALID_INFERENCE_DEVICES = frozenset({"auto", "cpu", "coreml", "cuda"})

_configured_threads = 1
_active_label = "CPU"


def _intra_op_threads(total_workers: int = 1) -> int:
    if ONNX_INTRA_OP_THREADS > 0:
        base = ONNX_INTRA_OP_THREADS
    else:
        base = max(1, min(8, os.cpu_count() or 4))
    workers = max(1, total_workers)
    return max(1, base // workers)


def configure_cpu_threads(total_workers: int = 1) -> int:
    """Limit BLAS/OpenMP threads so ONNX intra-op threads are not oversubscribed."""
    global _configured_threads
    threads = _intra_op_threads(total_workers)
    _configured_threads = threads
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ[var] = str(threads)
    return threads


configure_cpu_threads()


def available_accelerators() -> dict[str, bool]:
    import onnxruntime as ort

    providers = set(ort.get_available_providers())
    return {
        "coreml": "CoreMLExecutionProvider" in providers,
        "cuda": "CUDAExecutionProvider" in providers,
    }


def requested_inference_device() -> str:
    raw = os.environ.get(ENV_INFERENCE_DEVICE, INFERENCE_DEVICE).strip().lower()
    if raw not in VALID_INFERENCE_DEVICES:
        return "auto"
    return raw


def resolved_inference_device(requested: str | None = None) -> str:
    """Map auto/coreml/cuda/cpu to a concrete backend available on this machine."""
    mode = (requested or requested_inference_device()).lower()
    if mode not in VALID_INFERENCE_DEVICES:
        mode = "auto"

    accelerators = available_accelerators()
    if mode == "auto":
        if accelerators["coreml"]:
            return "coreml"
        if accelerators["cuda"]:
            return "cuda"
        return "cpu"

    if mode == "coreml":
        if accelerators["coreml"]:
            return "coreml"
        logger.warning("CoreML GPU requested but unavailable; falling back to CPU")
        return "cpu"

    if mode == "cuda":
        if accelerators["cuda"]:
            return "cuda"
        logger.warning("CUDA GPU requested but unavailable; falling back to CPU")
        return "cpu"

    return "cpu"


def inference_device_label(device: str | None = None) -> str:
    resolved = resolved_inference_device(device)
    return {
        "coreml": "Apple GPU (CoreML)",
        "cuda": "NVIDIA GPU (CUDA)",
        "cpu": "CPU",
    }[resolved]


def active_inference_label() -> str:
    return _active_label


def configure_inference_device(device: str) -> str:
    """Persist device choice for this process and worker children; reload model."""
    normalized = device.strip().lower()
    if normalized not in VALID_INFERENCE_DEVICES:
        normalized = "auto"
    os.environ[ENV_INFERENCE_DEVICE] = normalized
    get_face_analysis.cache_clear()
    return resolved_inference_device(normalized)


def _execution_providers(resolved: str) -> tuple[list[Any], int, str]:
    threads = _configured_threads
    if resolved == "coreml":
        return (
            [
                (
                    "CoreMLExecutionProvider",
                    {
                        "ModelFormat": "MLProgram",
                        "MLComputeUnits": "CPUAndGPU",
                    },
                ),
                ("CPUExecutionProvider", {"intra_op_num_threads": threads}),
            ],
            0,
            "Apple GPU (CoreML)",
        )

    if resolved == "cuda":
        return (
            [
                ("CUDAExecutionProvider", {}),
                ("CPUExecutionProvider", {"intra_op_num_threads": threads}),
            ],
            0,
            "NVIDIA GPU (CUDA)",
        )

    return (
        [("CPUExecutionProvider", {"intra_op_num_threads": threads})],
        -1,
        "CPU",
    )


@lru_cache(maxsize=1)
def get_face_analysis() -> Any:
    from insightface.app import FaceAnalysis

    global _active_label
    resolved = resolved_inference_device()
    providers, ctx_id, label = _execution_providers(resolved)
    app = FaceAnalysis(name=INSIGHTFACE_MODEL, providers=providers)
    app.prepare(ctx_id=ctx_id, det_size=INSIGHTFACE_DET_SIZE)
    _active_label = label
    logger.info("InsightFace loaded with %s", label)
    return app

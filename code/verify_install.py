#!/usr/bin/env python3
"""Quick health check after installation."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))


def main() -> int:
    for name in ("numpy", "PIL", "cv2", "onnxruntime", "insightface", "customtkinter"):
        try:
            importlib.import_module(name)
        except ImportError as exc:
            print(f"Missing package {name}: {exc}", file=sys.stderr)
            return 1

    try:
        import tkinter  # noqa: F401
    except ImportError as exc:
        print(f"Missing tkinter (GUI): {exc}", file=sys.stderr)
        return 1

    try:
        from insightface.app import FaceAnalysis

        from config import INSIGHTFACE_DET_SIZE, INSIGHTFACE_MODEL

        app = FaceAnalysis(name=INSIGHTFACE_MODEL, providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=INSIGHTFACE_DET_SIZE)
    except Exception as exc:  # noqa: BLE001
        print(f"InsightFace model load failed: {exc}", file=sys.stderr)
        return 1

    print("Eliseus Sorter ready (InsightFace + GUI).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

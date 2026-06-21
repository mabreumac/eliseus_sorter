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
        from face_engine import active_inference_label, configure_inference_device, get_face_analysis

        configure_inference_device("auto")
        get_face_analysis()
    except Exception as exc:  # noqa: BLE001
        print(f"InsightFace model load failed: {exc}", file=sys.stderr)
        return 1

    print(f"Eliseus Sorter ready (InsightFace on {active_inference_label()} + GUI).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

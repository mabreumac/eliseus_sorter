#!/usr/bin/env python3
"""Quick health check after installation."""

from __future__ import annotations

import importlib
import os
import sys

MIN_MODEL_BYTES = 1_000_000
MODEL_NAME = "dlib_face_recognition_resnet_model_v1.dat"


def _model_dat_path() -> str:
    import face_recognition_models

    return os.path.join(
        os.path.dirname(face_recognition_models.__file__),
        "models",
        MODEL_NAME,
    )


def _check_model_files() -> str | None:
    try:
        path = _model_dat_path()
    except Exception as exc:  # noqa: BLE001
        return f"face_recognition_models error: {exc}"

    if not os.path.isfile(path):
        return f"model file missing: {path}"
    size = os.path.getsize(path)
    if size < MIN_MODEL_BYTES:
        return (
            f"model file incomplete ({size} bytes): {path} — "
            "re-run Install.command"
        )
    return None


def main() -> int:
    for name in ("numpy", "pandas", "PIL", "tkinter", "customtkinter", "dlib", "pkg_resources"):
        try:
            importlib.import_module(name)
        except ImportError as exc:
            print(f"Missing package {name}: {exc}", file=sys.stderr)
            return 1

    model_error = _check_model_files()
    if model_error:
        print(model_error, file=sys.stderr)
        return 1

    try:
        importlib.import_module("face_recognition")
    except SystemExit:
        print("face_recognition exited while loading", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"face_recognition error: {exc}", file=sys.stderr)
        return 1

    print("All required packages and model files are available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

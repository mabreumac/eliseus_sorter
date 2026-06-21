#!/usr/bin/env python3
"""Install and verify face_recognition_models with full binary files."""

from __future__ import annotations

import os
import subprocess
import sys

MODEL_NAME = "dlib_face_recognition_resnet_model_v1.dat"
MIN_BYTES = 1_000_000
PACKAGE = "face_recognition_models==0.3.0"


def model_dat_path() -> str:
    import face_recognition_models

    return os.path.join(
        os.path.dirname(face_recognition_models.__file__),
        "models",
        MODEL_NAME,
    )


def models_ok() -> tuple[bool, str]:
    try:
        path = model_dat_path()
    except Exception as exc:  # noqa: BLE001
        return False, f"cannot import face_recognition_models: {exc}"

    if not os.path.isfile(path):
        return False, f"model file missing: {path}"
    size = os.path.getsize(path)
    if size < MIN_BYTES:
        return False, f"model file too small ({size} bytes): {path}"
    return True, path


def pip_install_models() -> None:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--upgrade", "setuptools>=65.0.0"],
    )
    subprocess.check_call(
        [sys.executable, "-m", "pip", "uninstall", "-y", "face_recognition_models"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--force-reinstall",
            PACKAGE,
        ],
    )


def ensure_setuptools() -> None:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--upgrade", "setuptools>=65.0.0"],
    )
    try:
        import pkg_resources  # noqa: F401
        return
    except ImportError:
        pass
    # Some Python builds need an explicit legacy-friendly setuptools pin.
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--force-reinstall", "setuptools==69.5.1"],
    )
    import pkg_resources  # noqa: F401


def main() -> int:
    ensure_setuptools()
    ok, detail = models_ok()
    if ok:
        print(f"face_recognition_models OK ({detail})")
        return 0

    print(f"Model check failed: {detail}", file=sys.stderr)
    print("Downloading face_recognition_models from PyPI (no cache)…", file=sys.stderr)
    pip_install_models()

    ok, detail = models_ok()
    if not ok:
        print(f"Still broken after reinstall: {detail}", file=sys.stderr)
        return 1

    print(f"face_recognition_models installed ({detail})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

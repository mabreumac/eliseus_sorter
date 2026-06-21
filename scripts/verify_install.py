#!/usr/bin/env python3
"""Quick health check after installation."""

from __future__ import annotations

import importlib
import sys

REQUIRED = (
    "numpy",
    "pandas",
    "PIL",
    "customtkinter",
    "face_recognition",
    "dlib",
)


def main() -> int:
    missing: list[str] = []
    for name in REQUIRED:
        try:
            importlib.import_module(name)
        except ImportError:
            missing.append(name)

    if missing:
        print("Missing packages:", ", ".join(missing), file=sys.stderr)
        return 1

    print("All required packages are available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

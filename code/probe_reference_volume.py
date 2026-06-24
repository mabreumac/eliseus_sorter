#!/usr/bin/env python3
"""Probe naming-reference images on a folder (e.g. external volume)."""

from __future__ import annotations

import sys
from pathlib import Path

# Run from repo: python probe_reference_volume.py [/path/to/JDM_PRINT_2024_25]
ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/Volumes/março_2026/JDM_PRINT_2024_25").expanduser()
SKIP = int(sys.argv[2]) if len(sys.argv) > 2 else 1

sys.path.insert(0, str(Path(__file__).resolve().parent))

from image_utils import describe_image_read_probe, iter_images_recursive, load_image_bgr
from naming_reference import _group_images_by_student_name, _first_single_face_in_images
from embeddings import FaceFilterParams


def main() -> int:
    print(f"Root: {ROOT}")
    print(f"Exists: {ROOT.is_dir()}")
    if not ROOT.is_dir():
        return 1

    images = list(iter_images_recursive(ROOT))
    print(f"Images found: {len(images)}")
    if not images:
        return 1

    for sample in images[:5]:
        print(f"  probe {describe_image_read_probe(sample)}")

    readable = sum(1 for p in images[:50] if load_image_bgr(p) is not None)
    print(f"Readable in first 50: {readable}/50")

    groups = _group_images_by_student_name(ROOT, SKIP)
    print(f"Names from layout (skip={SKIP}): {len(groups)}")
    if groups:
        first_name, first_paths = next(iter(groups.items()))
        print(f"  example: {first_name!r} ({len(first_paths)} photos)")
        emb, src, no_f, multi_f, read_err = _first_single_face_in_images(
            first_paths[:10], face_filter=FaceFilterParams()
        )
        print(
            f"  first student try: embedding={'yes' if emb is not None else 'no'}, "
            f"no_face={no_f}, multi={multi_f}, read_err={read_err}"
        )
        if src:
            print(f"  source: {src}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build a flat, scrambled test subset from ground truth (keeps original filenames)."""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

CODE = Path(__file__).resolve().parent
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

from app_paths import benchmark_data_dir, results_dir
from image_utils import IMAGE_EXTENSIONS, iter_ground_truth_images

DEFAULT_GROUND_TRUTH = benchmark_data_dir() / "ground_truth"
DEFAULT_TEST_SUBSET = benchmark_data_dir() / "test_subset"
DEFAULT_MANIFEST = results_dir() / "test_subset_manifest.json"


def _clear_images(directory: Path) -> None:
    if not directory.is_dir():
        directory.mkdir(parents=True, exist_ok=True)
        return
    for path in directory.iterdir():
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            path.unlink()


def build_test_subset(
    ground_truth_dir: Path,
    test_subset_dir: Path,
    manifest_path: Path,
    *,
    seed: int = 42,
) -> int:
    entries = list(iter_ground_truth_images(ground_truth_dir, include_group_folder=True))
    if not entries:
        raise ValueError(f"No images found under {ground_truth_dir}")

    rng = random.Random(seed)
    rng.shuffle(entries)

    _clear_images(test_subset_dir)
    test_subset_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[dict[str, str]] = []
    for student, source_path in entries:
        dest_name = source_path.name
        dest_path = test_subset_dir / dest_name
        if dest_path.exists():
            raise ValueError(
                f"Duplicate filename {dest_name!r} — cannot flatten ground truth "
                "with original names. Rename one copy first."
            )
        shutil.copy2(source_path, dest_path)
        manifest_rows.append(
            {
                "test_file": dest_name,
                "expected_student": student,
            }
        )

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_ground_truth": str(ground_truth_dir.resolve()),
        "test_subset_dir": str(test_subset_dir.resolve()),
        "seed": seed,
        "preserve_filenames": True,
        "total_images": len(manifest_rows),
        "images": manifest_rows,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return len(manifest_rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ground-truth", type=Path, default=DEFAULT_GROUND_TRUTH)
    parser.add_argument("--test-subset", type=Path, default=DEFAULT_TEST_SUBSET)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    count = build_test_subset(
        args.ground_truth.expanduser().resolve(),
        args.test_subset.expanduser().resolve(),
        args.manifest.expanduser().resolve(),
        seed=args.seed,
    )
    print(f"Built {count} images in {args.test_subset} (original filenames kept)")
    print(f"Label map: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

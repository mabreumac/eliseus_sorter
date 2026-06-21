#!/usr/bin/env python3
"""Balance ground_truth: even photo counts per student, fewer group photos."""

from __future__ import annotations

import argparse
import random
import shutil
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

from app_paths import benchmark_data_dir
from group_photos import is_group_reference_folder
from image_utils import IMAGE_EXTENSIONS, iter_image_files

DEFAULT_GROUND_TRUTH = benchmark_data_dir() / "ground_truth"
DEFAULT_ARCHIVE = benchmark_data_dir() / "ground_truth_archive"


def _list_images(folder: Path) -> list[Path]:
    return sorted(iter_image_files(folder), key=lambda p: p.name)


def balance_ground_truth(
    ground_truth_dir: Path,
    archive_dir: Path,
    *,
    per_student: int,
    group_photos: int,
    seed: int = 42,
    dry_run: bool = False,
) -> dict[str, int]:
    if not ground_truth_dir.is_dir():
        raise FileNotFoundError(ground_truth_dir)

    rng = random.Random(seed)
    kept_counts: dict[str, int] = {}
    moved_total = 0

    for student_dir in sorted(ground_truth_dir.iterdir()):
        if not student_dir.is_dir():
            continue

        images = _list_images(student_dir)
        if not images:
            continue

        limit = group_photos if is_group_reference_folder(student_dir.name) else per_student
        if len(images) <= limit:
            kept_counts[student_dir.name] = len(images)
            continue

        rng.shuffle(images)
        keep = sorted(images[:limit], key=lambda p: p.name)
        remove = images[limit:]
        kept_counts[student_dir.name] = len(keep)

        for path in remove:
            rel = path.relative_to(ground_truth_dir)
            dest = archive_dir / rel
            if dry_run:
                print(f"Would archive: {rel}")
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    dest.unlink()
                shutil.move(str(path), str(dest))
            moved_total += 1

    kept_counts["_archived"] = moved_total
    return kept_counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ground-truth", type=Path, default=DEFAULT_GROUND_TRUTH)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument(
        "--per-student",
        type=int,
        default=15,
        help="Max photos per student folder (default: 15)",
    )
    parser.add_argument(
        "--group",
        type=int,
        default=15,
        help="Max photos in _group_photos folder (default: 15)",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    gt = args.ground_truth.expanduser().resolve()
    archive = args.archive.expanduser().resolve()

    if args.dry_run:
        print("Dry run — no files moved\n")

    counts = balance_ground_truth(
        gt,
        archive,
        per_student=args.per_student,
        group_photos=args.group,
        seed=args.seed,
        dry_run=args.dry_run,
    )

    archived = counts.pop("_archived", 0)
    print("Kept per folder:")
    for name in sorted(counts):
        print(f"  {name!r}: {counts[name]}")
    print(f"\nTotal kept: {sum(counts.values())}")
    if not args.dry_run:
        print(f"Archived: {archived} → {archive}")
        print("\nNext: python build_test_subset.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

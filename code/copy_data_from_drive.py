#!/usr/bin/env python3
"""Copy benchmark data from Google Drive into the dev repo.

Removes trash folders named _PRINT and 15X22 under the source tree before copying.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

TRASH_DIR_NAMES = {"_PRINT", "15X22"}

DEFAULT_DEST = Path(__file__).resolve().parent.parent / "data" / "benchmark"


def remove_trash_dirs(root: Path, dry_run: bool = False) -> list[Path]:
    removed: list[Path] = []
    if not root.is_dir():
        return removed
    for path in sorted(root.rglob("*")):
        if path.is_dir() and path.name in TRASH_DIR_NAMES:
            removed.append(path)
            if not dry_run:
                shutil.rmtree(path)
    return removed


def copy_tree(src: Path, dst: Path, dry_run: bool = False) -> None:
    if dry_run:
        print(f"Would copy: {src} -> {dst}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def detect_layout(source: Path) -> dict[str, Path]:
    """Map source subfolders to benchmark destinations."""
    mapping: dict[str, Path] = {}
    if not source.is_dir():
        raise FileNotFoundError(f"Source not found: {source}")

    children = [p for p in source.iterdir() if p.is_dir()]
    names = {p.name.lower(): p for p in children}

    if "ground_truth" in names:
        mapping["ground_truth"] = names["ground_truth"]
    if "test_subset" in names:
        mapping["test_subset"] = names["test_subset"]
    elif "input" in names:
        # Unsorted photos to evaluate against the reference index.
        mapping["test_subset"] = names["input"]

    # Explicit benchmark layout at source root.
    if mapping:
        return mapping

    # Single event folder: student subfolders = ground_truth.
    student_like = [
        p
        for p in children
        if p.name not in TRASH_DIR_NAMES and not p.name.startswith(".")
    ]
    has_nested_students = any(
        any(c.is_dir() for c in p.iterdir()) for p in student_like if p.is_dir()
    )
    if len(student_like) == 1 and has_nested_students:
        mapping["ground_truth"] = student_like[0]
        return mapping

    # Multiple top-level student folders.
    if student_like and all(
        any(f.suffix.lower() in {".jpg", ".jpeg", ".png"} for f in p.iterdir() if f.is_file())
        for p in student_like[: min(3, len(student_like))]
    ):
        mapping["ground_truth"] = source
        return mapping

    # Named event folders; pick first with student subfolders as ground_truth.
    for event in sorted(student_like, key=lambda p: p.name):
        subdirs = [c for c in event.iterdir() if c.is_dir() and c.name not in TRASH_DIR_NAMES]
        if subdirs:
            mapping["ground_truth"] = event
            break

    return mapping


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Source data folder")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    dest = args.dest.expanduser().resolve()

    print(f"Source: {source}")
    print(f"Dest:   {dest}")

    if not source.is_dir():
        print(f"ERROR: source directory does not exist: {source}", file=sys.stderr)
        return 1

    print("\nTop-level source entries:")
    for p in sorted(source.iterdir()):
        kind = "dir" if p.is_dir() else "file"
        print(f"  [{kind}] {p.name}")

    removed = remove_trash_dirs(source, dry_run=args.dry_run)
    print(f"\nRemoved {len(removed)} trash folder(s) ({', '.join(TRASH_DIR_NAMES)}):")
    for p in removed:
        print(f"  {p}")

    mapping = detect_layout(source)
    if not mapping:
        print("\nERROR: could not detect ground_truth layout under source.", file=sys.stderr)
        print("Expected either ground_truth/ + test_subset/, or per-student folders.", file=sys.stderr)
        return 1

    print("\nCopy plan:")
    for key, src_path in mapping.items():
        print(f"  {src_path} -> {dest / key}")

    for key, src_path in mapping.items():
        copy_tree(src_path, dest / key, dry_run=args.dry_run)

    reports = dest / "reports"
    if not args.dry_run:
        reports.mkdir(parents=True, exist_ok=True)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

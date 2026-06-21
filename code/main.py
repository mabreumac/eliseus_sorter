#!/usr/bin/env python3
"""
Production CLI — cluster photos from input folder into class/person folders.

  python main.py --input /path/to/photos --output /path/to/sorted
  python main.py --input /parent/with/subfolders --output /out
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import DEFAULT_INFERENCE_DEVICE, DEFAULT_MIN_CLASS_FACES, DEFAULT_NAMING_REFERENCE_SKIP, DEFAULT_SCAN_WORKERS, GROUP_OUTPUT_FOLDER, MATCH_TOLERANCE
from face_engine import configure_inference_device
from group_photos import GroupPhotoSettings
from production import BatchSortResult, SortConfig, run_sort
from reporting import format_result_line


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Eliseus Sorter — sort photos into class and person folders",
    )
    parser.add_argument("--input", "-i", type=Path, required=True)
    parser.add_argument("--output", "-o", type=Path, required=True)
    parser.add_argument(
        "--min-class-faces",
        type=int,
        default=DEFAULT_MIN_CLASS_FACES,
        metavar="N",
        help="Photos with more than N faces define a class (default: %(default)s)",
    )
    parser.add_argument(
        "--naming-reference",
        type=Path,
        default=None,
        metavar="DIR",
        help="Optional folder of single-face reference photos (one subfolder per person)",
    )
    parser.add_argument(
        "--flat",
        action="store_true",
        help="Legacy mode: Person_001 at output root (no class folders)",
    )
    parser.add_argument(
        "--naming-reference-skip",
        type=int,
        default=DEFAULT_NAMING_REFERENCE_SKIP,
        metavar="N",
        help="Wrapper folder levels between naming ref root and student names (default: %(default)s)",
    )
    parser.add_argument(
        "--duplicate-group-photos",
        action="store_true",
        help="Also copy group photos into each matched person folder (default: group folder only)",
    )
    parser.add_argument(
        "--scan-workers",
        type=int,
        default=DEFAULT_SCAN_WORKERS,
        choices=[1, 2, 3, 4],
        metavar="N",
        help="Parallel face-scan processes (1=safe, 2–4=faster, more RAM; default: %(default)s)",
    )
    parser.add_argument(
        "--inference-device",
        choices=["auto", "cpu", "coreml", "cuda"],
        default=DEFAULT_INFERENCE_DEVICE,
        help="Inference backend: auto (GPU if available), cpu, coreml (Apple), cuda (NVIDIA)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def _print_result(result: object) -> None:
    print(f"\nSorted into: {result.output_dir}")
    if result.num_classes:
        print(f"  Classes:         {result.num_classes}")
    print(f"  Person clusters: {result.num_clusters}")
    print(f"  File copies:     {result.matched_count} matched, {result.unmatched_count} unmatched")
    if result.log_path:
        print(f"  Log: {result.log_path}")
    if result.person_renames:
        print("  Named clusters:")
        for generic, named in sorted(result.person_renames.items()):
            print(f"    {generic} → {named}")
    for item in result.results[:20]:
        print(format_result_line(item))
    if len(result.results) > 20:
        print(f"  … and {len(result.results) - 20} more (see log)")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _configure_logging(args.verbose)

    configure_inference_device(args.inference_device)

    config = SortConfig(
        input_dir=args.input,
        output_dir=args.output,
        tolerance=MATCH_TOLERANCE,
        min_class_faces=None if args.flat else args.min_class_faces,
        naming_reference=args.naming_reference,
        naming_reference_skip=args.naming_reference_skip,
        duplicate_group_photos=args.duplicate_group_photos,
        scan_workers=args.scan_workers,
        group_settings=GroupPhotoSettings(
            group_output_folder=GROUP_OUTPUT_FOLDER,
        ),
    )

    outcome = run_sort(config)
    if isinstance(outcome, BatchSortResult):
        print(f"\n{len(outcome.runs)} run(s) under: {outcome.output_dir}")
        for run in outcome.runs:
            _print_result(run)
    else:
        _print_result(outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

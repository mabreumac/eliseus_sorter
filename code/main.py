#!/usr/bin/env python3
"""
Production CLI — cluster photos from input folder into person folders.

  python main.py --input /path/to/photos --output /path/to/sorted
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import GROUP_OUTPUT_FOLDER, MATCH_TOLERANCE
from group_photos import GroupPhotoMode, GroupPhotoSettings
from production import SortConfig, run_sort
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
        description="Eliseus Sorter — cluster photos into Person_XXX folders",
    )
    parser.add_argument("--input", "-i", type=Path, required=True)
    parser.add_argument("--output", "-o", type=Path, required=True)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _configure_logging(args.verbose)

    config = SortConfig(
        input_dir=args.input,
        output_dir=args.output,
        tolerance=MATCH_TOLERANCE,
        group_settings=GroupPhotoSettings(
            mode=GroupPhotoMode.ALL_FACES,
            group_output_folder=GROUP_OUTPUT_FOLDER,
        ),
    )

    result = run_sort(config)
    print(f"\nSorted into: {result.output_dir}")
    print(f"  Person clusters: {result.num_clusters}")
    print(f"  File copies:     {result.matched_count} matched, {result.unmatched_count} unmatched")
    if result.log_path:
        print(f"  Log: {result.log_path}")
    for item in result.results[:20]:
        print(format_result_line(item))
    if len(result.results) > 20:
        print(f"  … and {len(result.results) - 20} more (see log)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

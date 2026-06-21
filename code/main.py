#!/usr/bin/env python3
"""
Eliseus Sorter — face-matching pipeline for school photos.

Phases:
  1. build   — Index ground_truth/ embeddings into SQLite
  2. match   — Compare test_subset/ images against the reference DB
  3. all     — Run build then match (default)

GUI:
  python gui_app.py

Data layout (under data/):
  ground_truth/<student_name>/<image>.jpg
  test_subset/<unassigned_image>.jpg
  school_photos.db
  output/match_report_<timestamp>.{json,csv}
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import DATABASE_PATH, GROUND_TRUTH_DIR, MATCH_TOLERANCE, OUTPUT_DIR, TEST_SUBSET_DIR
from database import count_reference_faces, count_students
from pipeline import PipelineConfig, run_build_phase
from reporting import format_build_stats, print_aggregate_summary, print_summary_table, save_reports
from match_subset import match_test_subset


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _default_config() -> PipelineConfig:
    return PipelineConfig(
        ground_truth_dir=GROUND_TRUTH_DIR,
        test_subset_dir=TEST_SUBSET_DIR,
        database_path=DATABASE_PATH,
        output_dir=OUTPUT_DIR,
        tolerance=MATCH_TOLERANCE,
    )


def run_build() -> int:
    """Phase 1: build reference database."""
    stats = run_build_phase(_default_config())
    print("\n--- " + format_build_stats(stats) + " ---")
    print(f"  DB total rows:     {count_reference_faces()}")
    print(f"  Distinct students: {count_students()}")
    print(f"  Database:          {DATABASE_PATH}\n")
    if stats.error_messages:
        print("Error details:")
        for msg in stats.error_messages:
            print(f"  - {msg}")
    return 0


def run_match(tolerance: float) -> int:
    """Phase 2 & 3: match test subset and write reports."""
    config = PipelineConfig(
        ground_truth_dir=GROUND_TRUTH_DIR,
        test_subset_dir=TEST_SUBSET_DIR,
        database_path=DATABASE_PATH,
        output_dir=OUTPUT_DIR,
        tolerance=tolerance,
    )

    if count_reference_faces(config.database_path) == 0:
        print(
            "Reference database is empty. Run phase 'build' first after "
            f"adding photos to {GROUND_TRUTH_DIR}"
        )
        return 1

    results = match_test_subset(
        test_subset_dir=config.test_subset_dir,
        db_path=config.database_path,
        tolerance=config.tolerance,
    )

    if not results:
        print(f"No images found in {TEST_SUBSET_DIR}")
        return 0

    print_summary_table(results)
    json_path, csv_path = save_reports(results, output_dir=config.output_dir, tolerance=tolerance)
    from reporting import results_to_dataframe

    print_aggregate_summary(results_to_dataframe(results))
    print(f"Reports saved:\n  {json_path}\n  {csv_path}\n")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Eliseus Sorter: match unassigned photos against ground-truth students.",
    )
    parser.add_argument(
        "phase",
        nargs="?",
        default="all",
        choices=("build", "match", "all"),
        help="Pipeline phase to run (default: all)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=MATCH_TOLERANCE,
        help=f"Max Euclidean distance for a match (default: {MATCH_TOLERANCE})",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _configure_logging(args.verbose)

    if args.phase == "build":
        return run_build()
    if args.phase == "match":
        return run_match(args.tolerance)

    build_code = run_build()
    if build_code != 0:
        return build_code
    return run_match(args.tolerance)


if __name__ == "__main__":
    raise SystemExit(main())

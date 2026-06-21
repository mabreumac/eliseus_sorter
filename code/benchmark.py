#!/usr/bin/env python3
"""
Benchmark CLI — cluster-sort test photos and score against ground truth.

Ground truth is never used to sort — only to score accuracy afterward.

  python benchmark.py sort     # test_subset → output/Person_XXX/
  python benchmark.py score    # compare output to ground_truth by filename
  python benchmark.py all      # sort + score + charts in results/charts_*/

Rebuild scrambled input after ground_truth changes:
  python build_test_subset.py   # keeps original filenames (JDV_*.jpg)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark_metrics import BenchmarkRuntime
from benchmark_pipeline import (
    BENCHMARK_GROUND_TRUTH,
    BENCHMARK_OUTPUT,
    BENCHMARK_REPORTS,
    BENCHMARK_TEST_SUBSET,
    BenchmarkConfig,
    run_benchmark_score,
    run_benchmark_sort,
)
from config import GROUP_OUTPUT_FOLDER, MATCH_TOLERANCE
from group_photos import GROUP_PHOTO_MODE_LABELS, GroupPhotoMode, GroupPhotoSettings
from reporting import print_aggregate_summary, print_output_folder_summary, results_to_dataframe


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _group_settings_from_args(args: argparse.Namespace) -> GroupPhotoSettings:
    mode = GroupPhotoMode(args.group_mode)
    folder = args.group_folder.strip() or GROUP_OUTPUT_FOLDER
    return GroupPhotoSettings(mode=mode, group_output_folder=folder)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Eliseus Sorter — benchmark clustering vs ground truth",
    )
    parser.add_argument(
        "phase",
        nargs="?",
        default="all",
        choices=("sort", "score", "all"),
    )
    parser.add_argument("--test-subset", type=Path, default=BENCHMARK_TEST_SUBSET)
    parser.add_argument("--ground-truth", type=Path, default=BENCHMARK_GROUND_TRUTH)
    parser.add_argument("--output", "-o", type=Path, default=BENCHMARK_OUTPUT)
    parser.add_argument("--reports", type=Path, default=BENCHMARK_REPORTS)
    parser.add_argument("--tolerance", type=float, default=MATCH_TOLERANCE)
    parser.add_argument(
        "--group-mode",
        choices=[m.value for m in GroupPhotoMode],
        default=GroupPhotoMode.ALL_FACES.value,
        help="Multi-face: use all_faces to also file group photos into person folders",
    )
    parser.add_argument("--group-folder", default=GROUP_OUTPUT_FOLDER)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _configure_logging(args.verbose)

    config = BenchmarkConfig(
        ground_truth_dir=args.ground_truth,
        test_subset_dir=args.test_subset,
        output_dir=args.output,
        reports_dir=args.reports,
        tolerance=args.tolerance,
        group_settings=_group_settings_from_args(args),
    )

    sort_result = None
    bench_runtime = BenchmarkRuntime()
    if args.phase in ("sort", "all"):
        sort_result = run_benchmark_sort(config)
        bench_runtime.sort = sort_result.runtime
        df = results_to_dataframe(sort_result.results)
        print_aggregate_summary(df)
        print_output_folder_summary(config.output_dir)
        rt = sort_result.runtime
        print(f"\nDiscovered {sort_result.num_clusters} person cluster(s)")
        print(
            f"Runtime: scan {rt.scan_seconds:.1f}s | "
            f"cluster {rt.cluster_seconds:.1f}s | "
            f"copy {rt.copy_seconds:.1f}s"
        )
        print(f"Sort log: {sort_result.log_path}\n")

    if args.phase in ("score", "all"):
        if sort_result is None:
            from cluster_sort import SortResult
            from match_subset import MatchResult
            import pandas as pd
            from config import SORT_LOG_NAME

            log_path = config.output_dir / SORT_LOG_NAME
            if not log_path.is_file():
                raise SystemExit(f"No sort log at {log_path}. Run: python benchmark.py sort")
            df = pd.read_csv(log_path)
            results = [
                MatchResult(
                    test_file=row["test_file"],
                    test_path=row["test_path"],
                    matched_student=row["matched_student"],
                    distance=row.get("confidence_distance"),
                    num_faces=int(row["num_faces"]),
                    face_index=int(row["face_index"]) if pd.notna(row.get("face_index")) else None,
                    is_group_photo=bool(row.get("is_group_photo")),
                    sorted_copy_path=row.get("sorted_copy_path"),
                )
                for _, row in df.iterrows()
            ]
            sort_result = SortResult(results=results, output_dir=config.output_dir)

        run_benchmark_score(sort_result, config, runtime=bench_runtime)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

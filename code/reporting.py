"""Phase 3: Reporting and verification output."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from config import MATCH_TOLERANCE
from group_photos import GroupPhotoSettings
from match_subset import MatchResult

logger = logging.getLogger(__name__)


def results_to_dataframe(results: Iterable[MatchResult]) -> pd.DataFrame:
    """Convert match results into a verification-friendly DataFrame."""
    rows = [
        {
            "test_file": r.test_file,
            "test_path": r.test_path,
            "matched_student": r.matched_student,
            "confidence_distance": r.distance,
            "num_faces": r.num_faces,
            "face_index": r.face_index,
            "source_kind": r.source_kind,
            "is_group_photo": r.is_group_photo,
            "sorted_copy_path": r.sorted_copy_path,
            "reference_file": r.reference_file,
            "error": r.error,
        }
        for r in results
    ]
    return pd.DataFrame(rows)


def print_summary_table(results: Iterable[MatchResult]) -> None:
    """Print human-readable lines for quick visual verification."""
    print("\n" + "=" * 72)
    print("MATCH RESULTS")
    print("=" * 72)

    for result in results:
        if result.distance is not None:
            distance_str = f"{result.distance:.2f}"
        else:
            distance_str = "N/A"

        line = (
            f"[{result.test_file}] -> Matched to: [{result.matched_student}] "
            f"(Confidence Distance: {distance_str})"
        )
        print(line)

        if result.error:
            print(f"    Error: {result.error}")
        if result.reference_file:
            print(f"    Best reference: {Path(result.reference_file).name}")

    print("=" * 72 + "\n")


def save_reports(
    results: list[MatchResult],
    output_dir: Path,
    tolerance: float = MATCH_TOLERANCE,
    group_settings: GroupPhotoSettings | None = None,
) -> tuple[Path, Path]:
    """
    Write JSON and CSV reports without moving or renaming source images.

    Returns (json_path, csv_path).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"match_report_{timestamp}.json"
    csv_path = output_dir / f"match_report_{timestamp}.csv"

    df = results_to_dataframe(results)
    df.to_csv(csv_path, index=False)

    settings = group_settings or GroupPhotoSettings()
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "tolerance": tolerance,
        "group_photo_mode": settings.mode.value,
        "group_photos_dir": str(settings.resolved_group_photos_dir() or ""),
        "sort_to_student_folders": settings.sort_to_student_folders,
        "sorted_output_dir": str(settings.sorted_output_dir),
        "total_rows": len(results),
        "matches": df.to_dict(orient="records"),
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    logger.info("Wrote CSV report to %s", csv_path)
    logger.info("Wrote JSON report to %s", json_path)

    return json_path, csv_path


def format_result_line(result: MatchResult) -> str:
    """Single-line summary for console or GUI logs."""
    if result.distance is not None:
        distance_str = f"{result.distance:.2f}"
    else:
        distance_str = "N/A"
    face = ""
    if result.face_index is not None and result.num_faces > 1:
        face = f" face {result.face_index + 1}"
    return (
        f"[{result.test_file}{face}] -> {result.matched_student} "
        f"(distance: {distance_str})"
    )


def format_build_stats(stats: object) -> str:
    """Human-readable build summary."""
    lines = [
        "Reference build complete",
        f"  Scanned:              {stats.processed}",
        f"  New embeddings:       {stats.inserted}",
        f"  Skipped (checkpoint): {stats.skipped_existing}",
        f"  No face detected:     {stats.no_face}",
        f"  Skipped group photos: {getattr(stats, 'skipped_group', 0)}",
        f"  Errors:               {stats.errors}",
    ]
    if getattr(stats, "cancelled", False):
        lines.append("  Status:               Cancelled")
    return "\n".join(lines)


def print_aggregate_summary(df: pd.DataFrame) -> None:
    """Print counts grouped by matched student."""
    if df.empty:
        print("No test images were processed.")
        return

    print("Aggregate summary:")
    counts = df["matched_student"].value_counts()
    for student, count in counts.items():
        print(f"  {student}: {count}")

    known = df[~df["matched_student"].isin(["Unknown", "No Face Detected", "Skipped (Group Photo)"])]
    if not known.empty and known["confidence_distance"].notna().any():
        avg_dist = known["confidence_distance"].mean()
        print(f"\nMean distance (known matches): {avg_dist:.3f}")


def print_output_folder_summary(output_dir: Path) -> None:
    """Print per-folder file counts under a sorted output directory."""
    if not output_dir.is_dir():
        print(f"Output folder not found: {output_dir}")
        return

    print(f"\nSorted output: {output_dir}")
    folders = sorted(p for p in output_dir.iterdir() if p.is_dir())
    if not folders:
        print("  (empty)")
        return

    for folder in folders:
        count = sum(1 for f in folder.iterdir() if f.is_file())
        print(f"  {folder.name}: {count}")


def print_manifest_accuracy(df: pd.DataFrame, manifest_path: Path) -> None:
    """Compare match results to the local label manifest (if present)."""
    if not manifest_path.is_file() or df.empty:
        return

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    truth = {row["test_file"]: row["expected_student"] for row in payload.get("images", [])}
    if not truth:
        return

    labeled = df[df["test_file"].isin(truth)].copy()
    labeled["expected_student"] = labeled["test_file"].map(truth)
    labeled["correct"] = labeled["matched_student"] == labeled["expected_student"]

    matched = labeled[
        ~labeled["matched_student"].isin(["Unknown", "No Face Detected", "Skipped (Group Photo)"])
    ]
    correct = int(matched["correct"].sum()) if not matched.empty else 0

    print("\nAccuracy vs label manifest:")
    print(f"  Total input photos:     {len(labeled)}")
    print(f"  Matched to a student:   {len(matched)}")
    if matched.empty:
        print("  Correct assignments:    —")
    else:
        print(f"  Correct assignments:    {correct} / {len(matched)} ({100 * correct / len(matched):.1f}%)")
    no_face = int((labeled["matched_student"] == "No Face Detected").sum())
    print(f"  No face detected:       {no_face}")

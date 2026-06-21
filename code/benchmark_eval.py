"""Benchmark scoring: compare cluster folders to ground-truth by filename."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from config import GROUP_OUTPUT_FOLDER, IMAGE_EXTENSIONS
from group_photos import is_group_reference_folder
from image_utils import ground_truth_labels
from match_subset import NO_FACE_LABEL, MatchResult


@dataclass(frozen=True)
class ClusterMapping:
    person_id: str
    predicted_student: str
    votes: int
    total_in_cluster: int

    @property
    def purity(self) -> float:
        if self.total_in_cluster == 0:
            return 0.0
        return self.votes / self.total_in_cluster


@dataclass(frozen=True)
class ClusterProfile:
    folder: str
    filenames: list[str]
    label_counts: Counter[str]

    @property
    def dominant_label(self) -> str:
        if not self.label_counts:
            return "—"
        return self.label_counts.most_common(1)[0][0]

    @property
    def purity(self) -> float:
        if not self.filenames:
            return 0.0
        return self.label_counts[self.dominant_label] / len(self.filenames)


@dataclass(frozen=True)
class BenchmarkScore:
    total_photos: int
    correct: int
    accuracy: float
    no_face: int
    group_folder_hits: int
    mappings: list[ClusterMapping]
    profiles: list[ClusterProfile]
    misclassified: list[dict[str, str]]


def _is_group_expected(student: str) -> bool:
    return is_group_reference_folder(student)


def _destinations_by_file(results: list[MatchResult]) -> dict[str, list[str]]:
    by_file: dict[str, list[str]] = defaultdict(list)
    for result in results:
        if result.sorted_copy_path:
            folder = Path(result.sorted_copy_path).parent.name
            if folder not in by_file[result.test_file]:
                by_file[result.test_file].append(folder)
    return by_file


def _files_in_output_folder(output_dir: Path, folder_name: str) -> list[str]:
    folder = output_dir / folder_name
    if not folder.is_dir():
        return []
    return sorted(
        p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def build_cluster_profiles(
    output_dir: Path,
    labels: dict[str, str],
    group_folder: str = GROUP_OUTPUT_FOLDER,
) -> list[ClusterProfile]:
    profiles: list[ClusterProfile] = []
    if not output_dir.is_dir():
        return profiles

    for child in sorted(output_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        filenames = _files_in_output_folder(output_dir, child.name)
        counts: Counter[str] = Counter()
        for name in filenames:
            counts[labels.get(name, "Unknown")] += 1
        profiles.append(
            ClusterProfile(folder=child.name, filenames=filenames, label_counts=counts)
        )
    return profiles


def infer_cluster_mapping(
    results: list[MatchResult],
    labels: dict[str, str],
    group_folder: str = GROUP_OUTPUT_FOLDER,
) -> dict[str, str]:
    """Map Person_X → ground-truth student using filename labels."""
    votes: dict[str, Counter[str]] = defaultdict(Counter)
    destinations = _destinations_by_file(results)

    for filename, expected in labels.items():
        if _is_group_expected(expected):
            continue
        folders = destinations.get(filename, [])
        person_folders = [
            f for f in folders if f.startswith("Person_") and f != group_folder
        ]
        if len(person_folders) != 1:
            continue
        votes[person_folders[0]][expected] += 1

    return {
        person_id: counter.most_common(1)[0][0]
        for person_id, counter in votes.items()
        if counter
    }


def score_cluster_sort(
    results: list[MatchResult],
    labels: dict[str, str],
    output_dir: Path,
    group_folder: str = GROUP_OUTPUT_FOLDER,
) -> BenchmarkScore:
    destinations = _destinations_by_file(results)
    cluster_mapping = infer_cluster_mapping(results, labels, group_folder)
    profiles = build_cluster_profiles(output_dir, labels, group_folder)

    votes_by_person: dict[str, Counter[str]] = defaultdict(Counter)
    cluster_sizes: Counter[str] = Counter()
    for filename, expected in labels.items():
        if _is_group_expected(expected):
            continue
        for folder in destinations.get(filename, []):
            if folder.startswith("Person_"):
                votes_by_person[folder][expected] += 1
                cluster_sizes[folder] += 1

    mappings = [
        ClusterMapping(
            person_id=person_id,
            predicted_student=cluster_mapping.get(person_id, "—"),
            votes=votes_by_person[person_id].get(
                cluster_mapping.get(person_id, ""), 0
            ),
            total_in_cluster=cluster_sizes[person_id],
        )
        for person_id in sorted(cluster_sizes)
    ]

    correct = 0
    no_face = 0
    group_hits = 0
    misclassified: list[dict[str, str]] = []

    for filename, expected in labels.items():
        folders = destinations.get(filename, [])
        if _is_group_expected(expected):
            if group_folder in folders:
                correct += 1
                group_hits += 1
            else:
                misclassified.append(
                    {
                        "test_file": filename,
                        "expected": expected,
                        "got": ", ".join(folders) or "(none)",
                    }
                )
            continue

        person_folders = [f for f in folders if f.startswith("Person_")]
        if not person_folders and not folders:
            no_face += 1
            misclassified.append(
                {"test_file": filename, "expected": expected, "got": NO_FACE_LABEL}
            )
            continue

        if len(person_folders) == 1:
            predicted = cluster_mapping.get(person_folders[0], person_folders[0])
            if predicted == expected:
                correct += 1
            else:
                misclassified.append(
                    {
                        "test_file": filename,
                        "expected": expected,
                        "got": predicted,
                    }
                )
        elif group_folder in folders and not person_folders:
            misclassified.append(
                {
                    "test_file": filename,
                    "expected": expected,
                    "got": group_folder,
                }
            )
        else:
            predicted = ", ".join(
                cluster_mapping.get(p, p) for p in person_folders
            ) or ", ".join(folders)
            if expected in predicted:
                correct += 1
            else:
                misclassified.append(
                    {
                        "test_file": filename,
                        "expected": expected,
                        "got": predicted,
                    }
                )

    total = len(labels)
    accuracy = correct / total if total else 0.0
    return BenchmarkScore(
        total_photos=total,
        correct=correct,
        accuracy=accuracy,
        no_face=no_face,
        group_folder_hits=group_hits,
        mappings=mappings,
        profiles=profiles,
        misclassified=misclassified,
    )


def save_benchmark_score(
    score: BenchmarkScore,
    reports_dir: Path,
    cluster_mapping: dict[str, str],
    labels: dict[str, str],
) -> tuple[Path, Path, Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = reports_dir / f"benchmark_score_{timestamp}.json"
    mapping_csv = reports_dir / f"cluster_mapping_{timestamp}.csv"
    profile_csv = reports_dir / f"cluster_profiles_{timestamp}.csv"

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_photos": score.total_photos,
        "correct": score.correct,
        "accuracy": score.accuracy,
        "no_face": score.no_face,
        "group_folder_hits": score.group_folder_hits,
        "cluster_to_student": cluster_mapping,
        "mappings": [
            {
                "person_id": m.person_id,
                "predicted_student": m.predicted_student,
                "votes": m.votes,
                "total_in_cluster": m.total_in_cluster,
                "purity": m.purity,
            }
            for m in score.mappings
        ],
        "cluster_profiles": [
            {
                "folder": p.folder,
                "file_count": len(p.filenames),
                "dominant_student": p.dominant_label,
                "purity": p.purity,
                "label_counts": dict(p.label_counts),
            }
            for p in score.profiles
        ],
        "misclassified_sample": score.misclassified[:50],
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    pd.DataFrame(
        [
            {"person_id": person_id, "predicted_student": student}
            for person_id, student in sorted(cluster_mapping.items())
        ]
    ).to_csv(mapping_csv, index=False)

    profile_detail_rows: list[dict[str, object]] = []
    for profile in score.profiles:
        for student, count in profile.label_counts.items():
            profile_detail_rows.append(
                {
                    "output_folder": profile.folder,
                    "ground_truth_student": student,
                    "file_count": count,
                    "folder_purity": profile.purity,
                    "dominant_student": profile.dominant_label,
                }
            )
    pd.DataFrame(profile_detail_rows).to_csv(profile_csv, index=False)

    file_rows: list[dict[str, str]] = []
    for profile in score.profiles:
        for filename in profile.filenames:
            file_rows.append(
                {
                    "output_folder": profile.folder,
                    "filename": filename,
                    "ground_truth_student": labels.get(filename, "Unknown"),
                    "matches_dominant": labels.get(filename, "")
                    == profile.dominant_label,
                }
            )
    files_csv = reports_dir / f"cluster_files_{timestamp}.csv"
    pd.DataFrame(file_rows).to_csv(files_csv, index=False)

    return json_path, mapping_csv, profile_csv, files_csv


def print_benchmark_score(score: BenchmarkScore, cluster_mapping: dict[str, str]) -> None:
    print("\n" + "=" * 72)
    print("BENCHMARK SCORE (compare by original filename)")
    print("=" * 72)
    print(f"  Photos scored:     {score.total_photos}")
    print(f"  Correct:           {score.correct} ({100 * score.accuracy:.1f}%)")
    print(f"  No face / empty:   {score.no_face}")
    print(f"  Group folder OK:   {score.group_folder_hits}")

    print("\nCluster profiles (does each output folder contain the right person's photos?):")
    for profile in score.profiles:
        if profile.folder.startswith("Person_"):
            mapped = cluster_mapping.get(profile.folder, profile.dominant_label)
            print(
                f"\n  {profile.folder} → {mapped}  "
                f"({len(profile.filenames)} files, purity {100 * profile.purity:.0f}%)"
            )
        else:
            print(
                f"\n  {profile.folder}  "
                f"({len(profile.filenames)} files, purity {100 * profile.purity:.0f}%)"
            )
        for student, count in profile.label_counts.most_common(5):
            print(f"    {student}: {count}")

    if score.misclassified:
        print(f"\nMisplaced files (showing up to 10 of {len(score.misclassified)}):")
        for row in score.misclassified[:10]:
            print(f"  {row['test_file']}: expected {row['expected']!r}, got {row['got']!r}")
    print("=" * 72 + "\n")

"""Benchmark charts: runtime, accuracy, cluster purity, per-student recall."""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from benchmark_eval import BenchmarkScore
from benchmark_metrics import BenchmarkRuntime
from config import GROUP_OUTPUT_FOLDER, INSIGHTFACE_MODEL, MATCH_TOLERANCE


def per_student_recall(
    labels: dict[str, str],
    misclassified: list[dict[str, str]],
) -> list[dict[str, Any]]:
    mis_set = {(m["test_file"], m["expected"]) for m in misclassified}
    by_student: Counter[str] = Counter(labels.values())
    rows: list[dict[str, Any]] = []
    for student in sorted(by_student):
        total = by_student[student]
        wrong = sum(1 for f, exp in mis_set if exp == student)
        correct = total - wrong
        rows.append(
            {
                "student": student.strip(),
                "total": total,
                "correct": correct,
                "recall": correct / total if total else 0.0,
            }
        )
    return rows


def _student_matrix(profiles: list, labels: dict[str, str]) -> tuple[list[str], list[str], np.ndarray]:
    """Build ground-truth-student × output-folder count matrix for heatmap."""
    students = sorted({s.strip() for s in labels.values()})
    folders = [p.folder for p in profiles if p.folder.startswith("Person_") or p.folder == GROUP_OUTPUT_FOLDER]
    if not folders:
        return students, [], np.zeros((len(students), 0))

    matrix = np.zeros((len(students), len(folders)), dtype=int)
    folder_index = {name: i for i, name in enumerate(folders)}
    student_index = {name: i for i, name in enumerate(students)}

    for profile in profiles:
        if profile.folder not in folder_index:
            continue
        col = folder_index[profile.folder]
        for filename in profile.filenames:
            student = labels.get(filename, "Unknown").strip()
            if student in student_index:
                matrix[student_index[student], col] += 1
    return students, folders, matrix


def generate_benchmark_visualizations(
    score: BenchmarkScore,
    labels: dict[str, str],
    cluster_mapping: dict[str, str],
    runtime: BenchmarkRuntime,
    reports_dir: Path,
    *,
    tolerance: float = MATCH_TOLERANCE,
    num_clusters: int = 0,
) -> Path:
    """Write a dashboard PNG + manifest JSON; return dashboard path."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    chart_dir = reports_dir / f"charts_{timestamp}"
    chart_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    dashboard_path = chart_dir / "benchmark_dashboard.png"

    fig = plt.figure(figsize=(18, 11))
    fig.suptitle("Eliseus Sorter — Benchmark Report", fontsize=16, fontweight="bold", y=0.98)
    gs = fig.add_gridspec(2, 3, hspace=0.38, wspace=0.32)

    # --- 1. Runtime ---
    ax_rt = fig.add_subplot(gs[0, 0])
    phases = ["Face scan", "Cluster", "Copy/sort", "Score"]
    seconds = [
        runtime.sort.scan_seconds,
        runtime.sort.cluster_seconds,
        runtime.sort.copy_seconds,
        runtime.score_seconds,
    ]
    colors = ["#2D6A4F", "#40916C", "#52B788", "#74C69D"]
    bars = ax_rt.barh(phases, seconds, color=colors)
    ax_rt.set_xlabel("Seconds")
    ax_rt.set_title("Runtime by phase")
    for bar, sec in zip(bars, seconds):
        if sec > 0:
            ax_rt.text(bar.get_width() + 0.02, bar.get_y() + bar.get_height() / 2,
                       f"{sec:.1f}s", va="center", fontsize=9)
    total = runtime.total_seconds
    ax_rt.text(0.02, -0.18, f"Total: {total:.1f}s", transform=ax_rt.transAxes, fontsize=10)

    # --- 2. Overall accuracy ---
    ax_acc = fig.add_subplot(gs[0, 1])
    wrong = score.total_photos - score.correct - score.no_face
    sizes = [score.correct, wrong, score.no_face]
    pie_labels = ["Correct", "Wrong", "No face"]
    pie_colors = ["#2D6A4F", "#E76F51", "#ADB5BD"]
    nonzero = [(l, s, c) for l, s, c in zip(pie_labels, sizes, pie_colors) if s > 0]
    if nonzero:
        ax_acc.pie(
            [x[1] for x in nonzero],
            labels=[f"{x[0]}\n{x[1]}" for x in nonzero],
            colors=[x[2] for x in nonzero],
            autopct=lambda p: f"{p:.0f}%" if p > 5 else "",
            startangle=90,
        )
    ax_acc.set_title(f"Overall accuracy ({100 * score.accuracy:.1f}%)")

    # --- 3. Detection stats ---
    ax_det = fig.add_subplot(gs[0, 2])
    ax_det.axis("off")
    det_lines = [
        "Detection & clustering",
        "─" * 28,
        f"Photos input:      {runtime.sort.num_images}",
        f"Faces detected:    {runtime.sort.num_faces_detected}",
        f"Images w/ face:    {runtime.sort.num_images_with_face}",
        f"Images no face:    {runtime.sort.num_images_no_face}",
        f"Person clusters:   {num_clusters}",
        f"Similarity ≥:      {tolerance}",
        f"Backend:           InsightFace {INSIGHTFACE_MODEL}",
        "",
        f"Group folder OK:   {score.group_folder_hits}",
    ]
    ax_det.text(0.0, 1.0, "\n".join(det_lines), va="top", fontsize=10, family="monospace")

    # --- 4. Per-student recall ---
    ax_stu = fig.add_subplot(gs[1, 0])
    student_rows = per_student_recall(labels, score.misclassified)
    if student_rows:
        names = [r["student"] for r in student_rows]
        recalls = [100 * r["recall"] for r in student_rows]
        counts = [f"{r['correct']}/{r['total']}" for r in student_rows]
        y_pos = np.arange(len(names))
        bar_colors = ["#2D6A4F" if r >= 99 else "#40916C" if r >= 80 else "#E76F51" for r in recalls]
        ax_stu.barh(y_pos, recalls, color=bar_colors)
        ax_stu.set_yticks(y_pos)
        ax_stu.set_yticklabels(names, fontsize=8)
        ax_stu.set_xlim(0, 105)
        ax_stu.set_xlabel("Recall (%)")
        ax_stu.set_title("Per-student recall")
        for i, (r, c) in enumerate(zip(recalls, counts)):
            ax_stu.text(min(r + 1, 102), i, c, va="center", fontsize=7)
    else:
        ax_stu.text(0.5, 0.5, "No data", ha="center")

    # --- 5. Cluster purity (Person_* only, top 12 by size) ---
    ax_pur = fig.add_subplot(gs[1, 1])
    person_profiles = sorted(
        [p for p in score.profiles if p.folder.startswith("Person_")],
        key=lambda p: len(p.filenames),
        reverse=True,
    )[:12]
    if person_profiles:
        labels_p = []
        purities = []
        for p in person_profiles:
            mapped = cluster_mapping.get(p.folder, p.dominant_label.strip())
            labels_p.append(f"{p.folder}\n→ {mapped}")
            purities.append(100 * p.purity)
        x = np.arange(len(labels_p))
        bar_c = ["#2D6A4F" if pr >= 80 else "#E9C46A" if pr >= 50 else "#E76F51" for pr in purities]
        ax_pur.bar(x, purities, color=bar_c)
        ax_pur.set_xticks(x)
        ax_pur.set_xticklabels(labels_p, rotation=45, ha="right", fontsize=7)
        ax_pur.set_ylim(0, 105)
        ax_pur.set_ylabel("Purity (%)")
        ax_pur.set_title("Cluster purity (top 12)")
    else:
        ax_pur.text(0.5, 0.5, "No Person_* clusters", ha="center")

    # --- 6. Student × folder heatmap (compact) ---
    ax_hm = fig.add_subplot(gs[1, 2])
    students, folders, matrix = _student_matrix(score.profiles, labels)
    if matrix.size > 0:
        im = ax_hm.imshow(matrix, aspect="auto", cmap="YlGn")
        ax_hm.set_xticks(range(len(folders)))
        ax_hm.set_xticklabels(
            [f.replace("Person_", "P") if f.startswith("Person_") else f[:6] for f in folders],
            rotation=45, ha="right", fontsize=7,
        )
        ax_hm.set_yticks(range(len(students)))
        ax_hm.set_yticklabels(students, fontsize=7)
        ax_hm.set_title("Ground truth × output folder")
        fig.colorbar(im, ax=ax_hm, fraction=0.046, pad=0.04)
    else:
        ax_hm.text(0.5, 0.5, "No matrix data", ha="center")

    fig.savefig(dashboard_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    # Individual charts for quick sharing
    _save_runtime_chart(runtime, chart_dir / "runtime.png")
    _save_student_recall_chart(student_rows, chart_dir / "per_student_recall.png")

    runtime.viz_seconds = time.perf_counter() - t0

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dashboard": str(dashboard_path),
        "charts_dir": str(chart_dir),
        "runtime": {
            "scan_seconds": runtime.sort.scan_seconds,
            "cluster_seconds": runtime.sort.cluster_seconds,
            "copy_seconds": runtime.sort.copy_seconds,
            "score_seconds": runtime.score_seconds,
            "viz_seconds": runtime.viz_seconds,
            "total_seconds": runtime.total_seconds,
            "num_images": runtime.sort.num_images,
            "num_faces_detected": runtime.sort.num_faces_detected,
        },
        "accuracy": score.accuracy,
        "per_student_recall": student_rows,
    }
    (chart_dir / "charts_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return dashboard_path


def _save_runtime_chart(runtime: BenchmarkRuntime, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    labels = ["Scan", "Cluster", "Copy", "Score", "Viz"]
    values = [
        runtime.sort.scan_seconds,
        runtime.sort.cluster_seconds,
        runtime.sort.copy_seconds,
        runtime.score_seconds,
        runtime.viz_seconds,
    ]
    ax.bar(labels, values, color="#40916C")
    ax.set_ylabel("Seconds")
    ax.set_title("Benchmark runtime")
    for i, v in enumerate(values):
        if v > 0:
            ax.text(i, v + 0.05, f"{v:.1f}s", ha="center", fontsize=9)
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def _save_student_recall_chart(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        return
    fig, ax = plt.subplots(figsize=(8, max(4, len(rows) * 0.35)))
    names = [r["student"] for r in rows]
    recalls = [100 * r["recall"] for r in rows]
    ax.barh(names, recalls, color="#2D6A4F")
    ax.set_xlim(0, 105)
    ax.set_xlabel("Recall (%)")
    ax.set_title("Per-student recall")
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)

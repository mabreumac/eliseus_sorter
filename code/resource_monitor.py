"""Lightweight process-tree CPU and memory sampling (stdlib only, macOS-friendly)."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceSnapshot:
    memory_mb: float
    cpu_percent: float
    process_count: int


def _collect_pids(root_pid: int) -> set[int]:
    pids = {root_pid}
    frontier = [root_pid]
    while frontier:
        next_frontier: list[int] = []
        for pid in frontier:
            try:
                result = subprocess.run(
                    ["pgrep", "-P", str(pid)],
                    capture_output=True,
                    text=True,
                    timeout=0.5,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line.isdigit():
                    continue
                child = int(line)
                if child not in pids:
                    pids.add(child)
                    next_frontier.append(child)
        frontier = next_frontier
    return pids


def _ps_value(pid: int, field: str) -> float:
    try:
        result = subprocess.run(
            ["ps", "-o", f"{field}=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=0.5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0.0
    text = result.stdout.strip().replace(",", ".")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def snapshot_process_tree(pid: int | None = None) -> ResourceSnapshot:
    """RSS (MB) and CPU % summed over the app process and its children."""
    root = pid if pid is not None else os.getpid()
    pids = _collect_pids(root)
    rss_kb = sum(_ps_value(child, "rss") for child in pids)
    cpu_percent = sum(_ps_value(child, "%cpu") for child in pids)
    return ResourceSnapshot(
        memory_mb=rss_kb / 1024.0,
        cpu_percent=cpu_percent,
        process_count=len(pids),
    )


def format_memory(mb: float) -> str:
    if mb >= 1024:
        return f"{mb / 1024:.1f} GB"
    return f"{mb:.0f} MB"


def format_resource_line(
    snap: ResourceSnapshot,
    *,
    scan_workers: int = 1,
    elapsed_seconds: float | None = None,
    inference: str | None = None,
) -> str:
    parts: list[str] = []
    if inference:
        parts.append(inference)
    parts.extend([
        f"Memory {format_memory(snap.memory_mb)}",
        f"CPU {snap.cpu_percent:.0f}%",
        f"Workers {scan_workers}",
    ])
    if snap.process_count > 1:
        parts.append(f"{snap.process_count} processes")
    if elapsed_seconds is not None:
        parts.append(f"Elapsed {_format_duration(elapsed_seconds)}")
    return " · ".join(parts)


def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    if minutes:
        return f"{minutes}:{secs:02d}"
    return f"{secs}s"


format_duration = _format_duration

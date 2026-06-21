#!/usr/bin/env python3
"""Eliseus Sorter — production desktop app (input folder → sorted output)."""

from __future__ import annotations

import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from production import BatchSortResult, SortConfig

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import customtkinter as ctk

from app_paths import ensure_app_support, is_app_bundle, load_settings, save_settings
from branding import ACCENT_COLOR, ACCENT_HOVER, APP_NAME, APP_TAGLINE
from config import (
    DEFAULT_INFERENCE_DEVICE,
    DEFAULT_MIN_CLASS_FACES,
    DEFAULT_NAMING_REFERENCE_SKIP,
    DEFAULT_SCAN_WORKERS,
    GROUP_OUTPUT_FOLDER,
    MATCH_TOLERANCE,
)
from face_engine import (
    active_inference_label,
    available_accelerators,
    configure_inference_device,
)
from group_photos import GroupPhotoSettings
from reporting import format_result_line
from resource_monitor import format_resource_line, snapshot_process_tree

APP_TITLE = APP_NAME
WINDOW_SIZE = "720x780"
ACCENT = ACCENT_COLOR
ACCENT_HOVER = ACCENT_HOVER

PHASE_LABELS = {
    "scan": "Scanning faces",
    "cluster": "Clustering faces",
    "naming": "Indexing names",
    "naming_match": "Matching names",
    "sort": "Copying files",
}

SCAN_WORKER_CHOICES: tuple[tuple[str, int], ...] = (
    ("1 — safe (default)", 1),
    ("2 — balanced", 2),
    ("3 — fast", 3),
    ("4 — max speed", 4),
)
SCAN_WORKER_LABELS = [label for label, _ in SCAN_WORKER_CHOICES]
SCAN_WORKER_VALUES = {label: value for label, value in SCAN_WORKER_CHOICES}


def _inference_device_menu_choices() -> tuple[list[str], dict[str, str], dict[str, str]]:
    accelerators = available_accelerators()
    options: list[tuple[str, str]] = [
        ("Auto", "auto"),
        ("CPU only", "cpu"),
    ]
    if accelerators["coreml"]:
        options.append(("Apple GPU (CoreML)", "coreml"))
    if accelerators["cuda"]:
        options.append(("NVIDIA GPU (CUDA)", "cuda"))
    labels = [label for label, _ in options]
    label_to_value = {label: value for label, value in options}
    value_to_label = {value: label for label, value in options}
    return labels, label_to_value, value_to_label


class PathSelector(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTkBaseClass,
        label: str,
        initial: Path | str = "",
        **kwargs: object,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=label, width=120, anchor="w").grid(
            row=0, column=0, padx=(0, 8), sticky="w"
        )
        self._var = tk.StringVar(value=str(initial))
        self.entry = ctk.CTkEntry(self, textvariable=self._var)
        self.entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ctk.CTkButton(
            self,
            text="Browse…",
            width=90,
            command=self._browse,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
        ).grid(row=0, column=2)

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(
            title="Select folder",
            initialdir=self.path.parent if self.path.exists() else Path.home(),
        )
        if chosen:
            self._var.set(chosen)

    @property
    def path(self) -> Path:
        return Path(self._var.get().strip())


class EliseusSorterApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("green")
        self.title(APP_TITLE)
        self.geometry(WINDOW_SIZE)
        self.minsize(640, 520)

        if is_app_bundle():
            ensure_app_support()

        self._settings = load_settings()
        self._cancel_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._monitor_stop = threading.Event()
        self._sort_started_at: Optional[float] = None
        self._active_scan_workers = DEFAULT_SCAN_WORKERS
        self._ui_queue: queue.Queue = queue.Queue()

        self._build_layout()
        self._poll_ui_queue()

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, corner_radius=12)
        header.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        ctk.CTkLabel(
            header, text=APP_TITLE, font=ctk.CTkFont(size=26, weight="bold")
        ).grid(row=0, column=0, padx=20, pady=(16, 4), sticky="w")
        ctk.CTkLabel(
            header,
            text=APP_TAGLINE,
            font=ctk.CTkFont(size=13),
            text_color=("gray30", "gray70"),
            wraplength=660,
            justify="left",
        ).grid(row=1, column=0, padx=20, pady=(0, 16), sticky="w")

        paths = ctk.CTkFrame(self, corner_radius=12)
        paths.grid(row=1, column=0, padx=20, pady=8, sticky="ew")
        paths.grid_columnconfigure(0, weight=1)
        self.input_dir = PathSelector(
            paths, "Input", self._settings.get("input_dir", "")
        )
        self.input_dir.grid(row=0, column=0, padx=16, pady=(16, 6), sticky="ew")
        self.output_dir = PathSelector(
            paths, "Output", self._settings.get("output_dir", "")
        )
        self.output_dir.grid(row=1, column=0, padx=16, pady=(6, 6), sticky="ew")
        self.naming_reference_dir = PathSelector(
            paths,
            "Naming ref",
            self._settings.get("naming_reference", ""),
        )
        self.naming_reference_dir.grid(row=2, column=0, padx=16, pady=(6, 6), sticky="ew")

        naming_skip_row = ctk.CTkFrame(paths, fg_color="transparent")
        naming_skip_row.grid(row=3, column=0, padx=16, pady=(0, 6), sticky="ew")
        ctk.CTkLabel(naming_skip_row, text="Ref folder skip", width=120, anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        self.naming_reference_skip_var = tk.StringVar(
            value=str(
                self._settings.get("naming_reference_skip", DEFAULT_NAMING_REFERENCE_SKIP)
            )
        )
        self.naming_reference_skip_entry = ctk.CTkEntry(
            naming_skip_row, textvariable=self.naming_reference_skip_var, width=80
        )
        self.naming_reference_skip_entry.grid(row=0, column=1, sticky="w", padx=(0, 8))
        ctk.CTkLabel(
            naming_skip_row,
            text="Folder levels up from each photo to the identity label (0 = folder that holds the image)",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
        ).grid(row=0, column=2, sticky="w")

        class_row = ctk.CTkFrame(paths, fg_color="transparent")
        class_row.grid(row=4, column=0, padx=16, pady=(0, 6), sticky="ew")
        ctk.CTkLabel(class_row, text="Group if faces >", width=120, anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        self.min_class_faces_var = tk.StringVar(
            value=str(self._settings.get("min_class_faces", DEFAULT_MIN_CLASS_FACES))
        )
        ctk.CTkEntry(class_row, textvariable=self.min_class_faces_var, width=80).grid(
            row=0, column=1, sticky="w", padx=(0, 8)
        )
        ctk.CTkLabel(
            class_row,
            text="Large group images seed roster clusters; input subfolders → separate runs",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
        ).grid(row=0, column=2, sticky="w")

        options_row = ctk.CTkFrame(paths, fg_color="transparent")
        options_row.grid(row=5, column=0, padx=16, pady=(0, 12), sticky="ew")
        self.duplicate_group_photos_var = tk.BooleanVar(
            value=bool(self._settings.get("duplicate_group_photos", False))
        )
        self.duplicate_group_checkbox = ctk.CTkCheckBox(
            options_row,
            text="Duplicate group photos into person folders",
            variable=self.duplicate_group_photos_var,
        )
        self.duplicate_group_checkbox.grid(row=0, column=0, sticky="w")

        workers_row = ctk.CTkFrame(paths, fg_color="transparent")
        workers_row.grid(row=6, column=0, padx=16, pady=(0, 6), sticky="ew")
        ctk.CTkLabel(workers_row, text="Scan workers", width=120, anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        saved_workers = int(self._settings.get("scan_workers", DEFAULT_SCAN_WORKERS))
        saved_workers = max(1, min(4, saved_workers))
        default_label = next(
            label for label, value in SCAN_WORKER_CHOICES if value == saved_workers
        )
        self.scan_workers_var = tk.StringVar(value=default_label)
        self.scan_workers_menu = ctk.CTkOptionMenu(
            workers_row,
            variable=self.scan_workers_var,
            values=SCAN_WORKER_LABELS,
            width=180,
        )
        self.scan_workers_menu.grid(row=0, column=1, sticky="w", padx=(0, 8))
        ctk.CTkLabel(
            workers_row,
            text="More workers = faster scan, more RAM (~200 MB per extra worker)",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
        ).grid(row=0, column=2, sticky="w")

        accel_row = ctk.CTkFrame(paths, fg_color="transparent")
        accel_row.grid(row=7, column=0, padx=16, pady=(0, 6), sticky="ew")
        ctk.CTkLabel(accel_row, text="Acceleration", width=120, anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        (
            self.inference_device_labels,
            self.inference_device_values,
            self.inference_device_by_value,
        ) = _inference_device_menu_choices()
        saved_device = str(
            self._settings.get("inference_device", DEFAULT_INFERENCE_DEVICE)
        ).lower()
        if saved_device not in self.inference_device_by_value:
            saved_device = DEFAULT_INFERENCE_DEVICE
        self.inference_device_var = tk.StringVar(
            value=self.inference_device_by_value.get(saved_device, "Auto")
        )
        self.inference_device_menu = ctk.CTkOptionMenu(
            accel_row,
            variable=self.inference_device_var,
            values=self.inference_device_labels,
            width=180,
        )
        self.inference_device_menu.grid(row=0, column=1, sticky="w", padx=(0, 8))
        accel_hint = "Uses Apple/NVIDIA GPU when available (Auto)"
        if available_accelerators()["coreml"]:
            accel_hint = "Apple GPU (CoreML) available — Auto uses it"
        elif available_accelerators()["cuda"]:
            accel_hint = "NVIDIA GPU (CUDA) available — Auto uses it"
        else:
            accel_hint = "No GPU backend detected — CPU only on this Mac"
        ctk.CTkLabel(
            accel_row,
            text=accel_hint,
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
        ).grid(row=0, column=2, sticky="w")

        actions = ctk.CTkFrame(paths, fg_color="transparent")
        actions.grid(row=8, column=0, padx=16, pady=(0, 16), sticky="ew")
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(1, weight=1)
        self.sort_btn = ctk.CTkButton(
            actions,
            text="Sort photos",
            command=self._start_sort,
            fg_color="#1B4332",
            hover_color=ACCENT,
        )
        self.sort_btn.grid(row=0, column=0, padx=(0, 4), sticky="ew")
        self.cancel_btn = ctk.CTkButton(
            actions,
            text="Cancel",
            command=self._request_cancel,
            state="disabled",
            fg_color="#6C757D",
        )
        self.cancel_btn.grid(row=0, column=1, padx=(4, 0), sticky="ew")

        progress = ctk.CTkFrame(self, corner_radius=12)
        progress.grid(row=2, column=0, padx=20, pady=(8, 20), sticky="nsew")
        progress.grid_columnconfigure(0, weight=1)
        progress.grid_rowconfigure(4, weight=1)
        self.phase_label = ctk.CTkLabel(
            progress, text="Ready", font=ctk.CTkFont(size=14, weight="bold")
        )
        self.phase_label.grid(row=0, column=0, padx=16, pady=(14, 4), sticky="w")
        self.status_label = ctk.CTkLabel(
            progress,
            text="Output: class_001/PersonName or Person_001 without a naming reference.",
            anchor="w",
            wraplength=620,
        )
        self.status_label.grid(row=1, column=0, padx=16, pady=(0, 4), sticky="ew")
        self.resource_label = ctk.CTkLabel(
            progress,
            text="",
            anchor="w",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
        )
        self.resource_label.grid(row=2, column=0, padx=16, pady=(0, 8), sticky="ew")
        self.progress = ctk.CTkProgressBar(progress, progress_color=ACCENT)
        self.progress.grid(row=3, column=0, padx=16, pady=(0, 8), sticky="ew")
        self.progress.set(0)
        self.log_box = ctk.CTkTextbox(
            progress, font=ctk.CTkFont(family="Menlo", size=12)
        )
        self.log_box.grid(row=4, column=0, padx=16, pady=(0, 16), sticky="nsew")
        progress.grid_rowconfigure(4, weight=1)

    def _min_class_faces(self) -> int:
        try:
            value = int(self.min_class_faces_var.get().strip())
        except ValueError as exc:
            raise ValueError("Group face threshold must be a whole number.") from exc
        if value < 1:
            raise ValueError("Group face threshold must be at least 1.")
        return value

    def _naming_reference_skip(self) -> int:
        try:
            value = int(self.naming_reference_skip_var.get().strip())
        except ValueError as exc:
            raise ValueError("Ref folder skip must be a whole number.") from exc
        if value < 0:
            raise ValueError("Ref folder skip must be 0 or greater.")
        return value

    def _scan_workers(self) -> int:
        label = self.scan_workers_var.get()
        return SCAN_WORKER_VALUES.get(label, DEFAULT_SCAN_WORKERS)

    def _inference_device(self) -> str:
        label = self.inference_device_var.get()
        return self.inference_device_values.get(label, DEFAULT_INFERENCE_DEVICE)

    def _naming_reference_path(self) -> Optional[Path]:
        raw = self.naming_reference_dir.path
        if not str(raw).strip():
            return None
        if not raw.is_dir():
            raise ValueError("Naming reference folder does not exist.")
        return raw

    def _sort_config(self) -> "SortConfig":
        from production import SortConfig

        return SortConfig(
            input_dir=self.input_dir.path,
            output_dir=self.output_dir.path,
            tolerance=MATCH_TOLERANCE,
            min_class_faces=self._min_class_faces(),
            naming_reference=self._naming_reference_path(),
            naming_reference_skip=self._naming_reference_skip(),
            duplicate_group_photos=self.duplicate_group_photos_var.get(),
            scan_workers=self._scan_workers(),
            group_settings=GroupPhotoSettings(
                group_output_folder=GROUP_OUTPUT_FOLDER,
            ),
        )

    def _persist_settings(self) -> None:
        save_settings(
            {
                "input_dir": str(self.input_dir.path),
                "output_dir": str(self.output_dir.path),
                "min_class_faces": self._min_class_faces(),
                "naming_reference": str(self.naming_reference_dir.path),
                "naming_reference_skip": self._naming_reference_skip(),
                "duplicate_group_photos": self.duplicate_group_photos_var.get(),
                "scan_workers": self._scan_workers(),
                "inference_device": self._inference_device(),
            }
        )

    def _set_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        self.sort_btn.configure(state=state)
        self.input_dir.entry.configure(state=state)
        self.output_dir.entry.configure(state=state)
        self.naming_reference_dir.entry.configure(state=state)
        self.naming_reference_skip_entry.configure(state=state)
        self.duplicate_group_checkbox.configure(state=state)
        self.scan_workers_menu.configure(state=state)
        self.inference_device_menu.configure(state=state)
        self.cancel_btn.configure(state="normal" if running else "disabled")

    def _request_cancel(self) -> None:
        self._cancel_event.set()

    def _on_close(self) -> None:
        if self._worker and self._worker.is_alive():
            self._cancel_event.set()
        self.destroy()

    def _run_on_ui(self, func: Callable[..., object], *args: object, **kwargs: object) -> None:
        self._ui_queue.put((func, args, kwargs))

    def _poll_ui_queue(self) -> None:
        while True:
            try:
                func, args, kwargs = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            func(*args, **kwargs)
        self.after(80, self._poll_ui_queue)

    def _append_log(self, msg: str) -> None:
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")

    def _on_progress(self, phase: str, current: int, total: int, message: str) -> None:
        self._run_on_ui(self._update_progress, phase, current, total, message)

    def _update_progress(self, phase: str, current: int, total: int, message: str) -> None:
        fraction = min(current / total if total else 0, 1.0)
        self.progress.set(fraction)
        phase_title = PHASE_LABELS.get(phase, "Sorting photos")
        percent = int(fraction * 100)
        self.phase_label.configure(text=f"{phase_title} — {percent}%")
        self.status_label.configure(text=f"{message}  ({current}/{total})")

    def _update_resources(self) -> None:
        if self._sort_started_at is None:
            return
        elapsed = time.perf_counter() - self._sort_started_at
        snap = snapshot_process_tree()
        self.resource_label.configure(
            text=format_resource_line(
                snap,
                scan_workers=self._active_scan_workers,
                elapsed_seconds=elapsed,
                inference=active_inference_label(),
            )
        )

    def _start_sort(self) -> None:
        if self._worker and self._worker.is_alive():
            messagebox.showwarning(APP_TITLE, "Already running.")
            return
        if not self.input_dir.path.is_dir():
            messagebox.showerror(APP_TITLE, "Input folder does not exist.")
            return
        if not self.output_dir.path:
            messagebox.showerror(APP_TITLE, "Choose an output folder.")
            return

        try:
            config = self._sort_config()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        device = self._inference_device()
        resolved = configure_inference_device(device)
        if resolved in {"coreml", "cuda"} and config.scan_workers > 1:
            if not messagebox.askyesno(
                APP_TITLE,
                "GPU acceleration works best with 1 scan worker.\n\n"
                f"You selected {config.scan_workers} workers, which loads the model "
                "multiple times and may use a lot of VRAM.\n\n"
                "Continue anyway?",
            ):
                return

        self._persist_settings()
        self._cancel_event.clear()
        self._monitor_stop.clear()
        self._sort_started_at = time.perf_counter()
        self._active_scan_workers = config.scan_workers
        self._set_running(True)
        self.progress.set(0)
        self.resource_label.configure(
            text=f"Loading model on {active_inference_label()}…"
        )
        self.log_box.delete("1.0", "end")
        self._worker = threading.Thread(
            target=self._worker_run, args=(config,), daemon=True
        )
        self._worker.start()
        threading.Thread(target=self._resource_monitor_loop, daemon=True).start()

    def _resource_monitor_loop(self) -> None:
        while not self._monitor_stop.wait(1.0):
            self._run_on_ui(self._update_resources)

    def _worker_run(self, config: "SortConfig") -> None:
        from production import run_sort

        try:
            outcome = run_sort(
                config,
                on_progress=self._on_progress,
                should_cancel=lambda: self._cancel_event.is_set(),
            )
            self._run_on_ui(self._finish, outcome)
        except Exception as exc:  # noqa: BLE001
            self._run_on_ui(self._finish_error, str(exc))
        finally:
            self._monitor_stop.set()

    def _format_runtime(self, runtime: object) -> str:
        return (
            f"Timing — scan {runtime.scan_seconds:.1f}s, "
            f"cluster {runtime.cluster_seconds:.1f}s, "
            f"copy {runtime.copy_seconds:.1f}s · "
            f"{runtime.num_faces_detected} faces in "
            f"{runtime.num_images_with_face}/{runtime.num_images} images"
        )

    def _log_result(self, result: object) -> None:
        self._append_log(f"Output: {result.output_dir}")
        if result.num_classes:
            self._append_log(f"Roster groups: {result.num_classes}")
        self._append_log(f"Person clusters: {result.num_clusters}")
        self._append_log(
            f"Copies: {result.matched_count} matched, {result.unmatched_count} unmatched"
        )
        if result.log_path:
            self._append_log(f"Log: {result.log_path}")
        if getattr(result, "runtime", None):
            self._append_log(self._format_runtime(result.runtime))
        if result.person_renames:
            self._append_log("Person names:")
            for generic, named in sorted(result.person_renames.items()):
                self._append_log(f"  {generic} → {named}")

    def _finish(self, outcome: object) -> None:
        from production import BatchSortResult

        in_place = self.input_dir.path.resolve() == self.output_dir.path.resolve()
        if isinstance(outcome, BatchSortResult):
            self._append_log(f"{len(outcome.runs)} run(s) under {outcome.output_dir}")
            for result in outcome.runs:
                self._append_log("")
                self._log_result(result)
                for item in result.results[:10]:
                    self._append_log(format_result_line(item))
        else:
            self._log_result(outcome)
            for item in outcome.results[:30]:
                self._append_log(format_result_line(item))

        self._set_running(False)
        self._sort_started_at = None
        self.phase_label.configure(text="Done")
        self._update_resources()
        if in_place:
            finish_text = (
                "Sorting finished. Photos were moved into subfolders "
                "(extra copies only where a file appears in multiple folders)."
            )
        else:
            finish_text = "Sorting finished. Original photos in the input folder were not changed."
        self.status_label.configure(text=finish_text)

    def _finish_error(self, message: str) -> None:
        self._append_log(f"ERROR: {message}")
        self._set_running(False)
        self._sort_started_at = None
        self.resource_label.configure(text="")
        messagebox.showerror(APP_TITLE, message)


def main() -> None:
    ensure_app_support()
    app = EliseusSorterApp()
    app.mainloop()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Desktop GUI for Eliseus Sorter (macOS-friendly).

Launch:
    cd code && python gui_app.py
"""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, Optional

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import customtkinter as ctk

from config import (
    DATABASE_PATH,
    GROUND_TRUTH_DIR,
    MATCH_TOLERANCE,
    OUTPUT_DIR,
    TEST_SUBSET_DIR,
)
from database import count_reference_faces, count_students
from pipeline import (
    PipelineConfig,
    run_build_phase,
    run_full_pipeline,
    run_match_phase,
)
from reporting import format_build_stats, format_result_line

APP_TITLE = "Eliseus Sorter"
WINDOW_SIZE = "980x760"
ACCENT = "#2D6A4F"
ACCENT_HOVER = "#40916C"


class PathSelector(ctk.CTkFrame):
    """Labeled path field with a native folder picker."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        label: str,
        initial: Path,
        **kwargs: object,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text=label, width=150, anchor="w").grid(
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
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("green")

        self.title(APP_TITLE)
        self.geometry(WINDOW_SIZE)
        self.minsize(860, 640)

        self._cancel_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._ui_queue: queue.Queue[tuple[Callable[[], None], tuple, dict]] = queue.Queue()

        self._build_layout()
        self._poll_ui_queue()

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(self, corner_radius=12)
        header.grid(row=0, column=0, padx=20, pady=(20, 12), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text=APP_TITLE,
            font=ctk.CTkFont(size=26, weight="bold"),
        ).grid(row=0, column=0, padx=20, pady=(16, 4), sticky="w")
        ctk.CTkLabel(
            header,
            text="Match unassigned school photos against your ground-truth student folders.",
            font=ctk.CTkFont(size=13),
            text_color=("gray30", "gray70"),
        ).grid(row=1, column=0, padx=20, pady=(0, 16), sticky="w")

        paths_card = ctk.CTkFrame(self, corner_radius=12)
        paths_card.grid(row=1, column=0, padx=20, pady=8, sticky="ew")
        paths_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            paths_card,
            text="Folders",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, padx=16, pady=(14, 8), sticky="w")

        self.ground_truth = PathSelector(
            paths_card, "Ground truth", GROUND_TRUTH_DIR
        )
        self.ground_truth.grid(row=1, column=0, padx=16, pady=6, sticky="ew")

        self.test_subset = PathSelector(paths_card, "Test subset", TEST_SUBSET_DIR)
        self.test_subset.grid(row=2, column=0, padx=16, pady=6, sticky="ew")

        self.database = PathSelector(paths_card, "Database", DATABASE_PATH)
        self.database.grid(row=3, column=0, padx=16, pady=6, sticky="ew")

        self.output_dir = PathSelector(paths_card, "Reports output", OUTPUT_DIR)
        self.output_dir.grid(row=4, column=0, padx=16, pady=(6, 14), sticky="ew")

        settings_card = ctk.CTkFrame(self, corner_radius=12)
        settings_card.grid(row=2, column=0, padx=20, pady=8, sticky="ew")
        settings_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            settings_card,
            text="Match tolerance",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, columnspan=3, padx=16, pady=(14, 4), sticky="w")

        self.tolerance_var = tk.DoubleVar(value=MATCH_TOLERANCE)
        self.tolerance_slider = ctk.CTkSlider(
            settings_card,
            from_=0.35,
            to=0.85,
            number_of_steps=50,
            variable=self.tolerance_var,
            command=self._on_tolerance_change,
            progress_color=ACCENT,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
        )
        self.tolerance_slider.grid(row=1, column=0, columnspan=2, padx=16, pady=8, sticky="ew")

        self.tolerance_label = ctk.CTkLabel(settings_card, text=self._tolerance_text())
        self.tolerance_label.grid(row=1, column=2, padx=16, pady=8)

        actions = ctk.CTkFrame(settings_card, fg_color="transparent")
        actions.grid(row=2, column=0, columnspan=3, padx=16, pady=(4, 14), sticky="ew")
        for col in range(4):
            actions.grid_columnconfigure(col, weight=1)

        self.build_btn = ctk.CTkButton(
            actions,
            text="Build reference",
            command=lambda: self._start_job("build"),
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
        )
        self.build_btn.grid(row=0, column=0, padx=4, pady=4, sticky="ew")

        self.match_btn = ctk.CTkButton(
            actions,
            text="Match photos",
            command=lambda: self._start_job("match"),
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
        )
        self.match_btn.grid(row=0, column=1, padx=4, pady=4, sticky="ew")

        self.all_btn = ctk.CTkButton(
            actions,
            text="Run all",
            command=lambda: self._start_job("all"),
            fg_color="#1B4332",
            hover_color=ACCENT,
        )
        self.all_btn.grid(row=0, column=2, padx=4, pady=4, sticky="ew")

        self.cancel_btn = ctk.CTkButton(
            actions,
            text="Cancel",
            command=self._request_cancel,
            state="disabled",
            fg_color="#6C757D",
            hover_color="#495057",
        )
        self.cancel_btn.grid(row=0, column=3, padx=4, pady=4, sticky="ew")

        progress_card = ctk.CTkFrame(self, corner_radius=12)
        progress_card.grid(row=3, column=0, padx=20, pady=8, sticky="nsew")
        progress_card.grid_columnconfigure(0, weight=1)
        progress_card.grid_rowconfigure(3, weight=1)

        self.phase_label = ctk.CTkLabel(
            progress_card,
            text="Ready",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.phase_label.grid(row=0, column=0, padx=16, pady=(14, 4), sticky="w")

        self.status_label = ctk.CTkLabel(
            progress_card,
            text="Choose folders, then run a phase.",
            anchor="w",
        )
        self.status_label.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")

        self.progress = ctk.CTkProgressBar(progress_card, progress_color=ACCENT)
        self.progress.grid(row=2, column=0, padx=16, pady=(0, 8), sticky="ew")
        self.progress.set(0)

        self.log_box = ctk.CTkTextbox(progress_card, font=ctk.CTkFont(family="Menlo", size=12))
        self.log_box.grid(row=3, column=0, padx=16, pady=(0, 16), sticky="nsew")
        progress_card.grid_rowconfigure(3, weight=1)

    def _tolerance_text(self) -> str:
        value = self.tolerance_var.get()
        hint = "strict" if value < 0.5 else "balanced" if value <= 0.65 else "lenient"
        return f"{value:.2f} ({hint})"

    def _on_tolerance_change(self, _value: float) -> None:
        self.tolerance_label.configure(text=self._tolerance_text())

    def _pipeline_config(self) -> PipelineConfig:
        return PipelineConfig(
            ground_truth_dir=self.ground_truth.path,
            test_subset_dir=self.test_subset.path,
            database_path=self.database.path,
            output_dir=self.output_dir.path,
            tolerance=float(self.tolerance_var.get()),
        )

    def _set_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        for widget in (
            self.build_btn,
            self.match_btn,
            self.all_btn,
            self.ground_truth.entry,
            self.test_subset.entry,
            self.database.entry,
            self.output_dir.entry,
            self.tolerance_slider,
        ):
            widget.configure(state=state)
        self.cancel_btn.configure(state="normal" if running else "disabled")

    def _request_cancel(self) -> None:
        self._cancel_event.set()
        self._append_log("Cancellation requested…")

    def _should_cancel(self) -> bool:
        return self._cancel_event.is_set()

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

    def _append_log(self, message: str) -> None:
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")

    def _update_progress(self, phase: str, current: int, total: int, message: str) -> None:
        fraction = current / total if total else 0
        self.progress.set(min(max(fraction, 0.0), 1.0))
        phase_title = "Building reference" if phase == "build" else "Matching photos"
        self.phase_label.configure(text=phase_title)
        self.status_label.configure(text=f"{message}  ({current}/{total})")

    def _on_progress(self, phase: str, current: int, total: int, message: str) -> None:
        self._run_on_ui(self._update_progress, phase, current, total, message)

    def _start_job(self, mode: str) -> None:
        if self._worker and self._worker.is_alive():
            messagebox.showwarning(APP_TITLE, "A job is already running.")
            return

        config = self._pipeline_config()
        if mode in ("build", "all") and not config.ground_truth_dir.is_dir():
            messagebox.showerror(APP_TITLE, "Ground truth folder does not exist.")
            return
        if mode in ("match", "all") and not config.test_subset_dir.is_dir():
            messagebox.showerror(APP_TITLE, "Test subset folder does not exist.")
            return

        self._cancel_event.clear()
        self._set_running(True)
        self.progress.set(0)
        self.log_box.delete("1.0", "end")
        self._append_log(f"Starting: {mode}")

        self._worker = threading.Thread(
            target=self._job_worker,
            args=(mode, config),
            daemon=True,
        )
        self._worker.start()

    def _job_worker(self, mode: str, config: PipelineConfig) -> None:
        try:
            if mode == "build":
                stats = run_build_phase(
                    config,
                    on_progress=self._on_progress,
                    should_cancel=self._should_cancel,
                )
                self._run_on_ui(self._finish_build, stats)
            elif mode == "match":
                result = run_match_phase(
                    config,
                    on_progress=self._on_progress,
                    should_cancel=self._should_cancel,
                )
                self._run_on_ui(self._finish_match, result)
            else:
                stats, result = run_full_pipeline(
                    config,
                    on_progress=self._on_progress,
                    should_cancel=self._should_cancel,
                )
                self._run_on_ui(self._finish_all, stats, result)
        except Exception as exc:  # noqa: BLE001 — surface pipeline errors in UI
            self._run_on_ui(self._finish_error, str(exc))

    def _finish_build(self, stats: object) -> None:
        self._append_log(format_build_stats(stats))
        self._append_log(
            f"Database rows: {count_reference_faces(self.database.path)} | "
            f"Students: {count_students(self.database.path)}"
        )
        self._set_running(False)
        self.phase_label.configure(text="Build complete")
        self.status_label.configure(text="Reference index updated.")

    def _finish_match(self, result: object) -> None:
        self._log_match_results(result)
        self._set_running(False)
        self.phase_label.configure(text="Match complete")
        self.status_label.configure(text="Review results below and open reports in output folder.")

    def _finish_all(self, stats: object, result: object) -> None:
        self._append_log(format_build_stats(stats))
        self._log_match_results(result)
        self._set_running(False)
        self.phase_label.configure(text="Pipeline complete")
        self.status_label.configure(text="Build and match finished.")

    def _log_match_results(self, result: object) -> None:
        if not result.results:
            self._append_log("No test images processed.")
            return
        self._append_log(f"\nMatched {len(result.results)} image(s):\n")
        for item in result.results:
            self._append_log(format_result_line(item))
        if result.json_path and result.csv_path:
            self._append_log(f"\nReports:\n  {result.json_path}\n  {result.csv_path}")

    def _finish_error(self, message: str) -> None:
        self._append_log(f"ERROR: {message}")
        self._set_running(False)
        self.phase_label.configure(text="Error")
        self.status_label.configure(text=message)
        messagebox.showerror(APP_TITLE, message)


def main() -> None:
    app = EliseusSorterApp()
    app.mainloop()


if __name__ == "__main__":
    main()

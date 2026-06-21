#!/usr/bin/env python3
"""Eliseus Sorter — production desktop app (input folder → sorted output)."""

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

from app_paths import ensure_app_support, is_app_bundle, load_settings, save_settings
from config import GROUP_OUTPUT_FOLDER, MATCH_TOLERANCE
from group_photos import GroupPhotoMode, GroupPhotoSettings
from production import SortConfig, run_sort
from reporting import format_result_line

APP_TITLE = "Eliseus Sorter"
WINDOW_SIZE = "720x560"
ACCENT = "#2D6A4F"
ACCENT_HOVER = "#40916C"


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
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("green")
        self.title(APP_TITLE)
        self.geometry(WINDOW_SIZE)
        self.minsize(640, 480)

        if is_app_bundle():
            ensure_app_support()

        self._settings = load_settings()
        self._cancel_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
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
            text="Pick a folder of photos and where to save sorted results.",
            font=ctk.CTkFont(size=13),
            text_color=("gray30", "gray70"),
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
        self.output_dir.grid(row=1, column=0, padx=16, pady=(6, 12), sticky="ew")

        actions = ctk.CTkFrame(paths, fg_color="transparent")
        actions.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="ew")
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
        progress.grid_rowconfigure(3, weight=1)
        self.phase_label = ctk.CTkLabel(
            progress, text="Ready", font=ctk.CTkFont(size=14, weight="bold")
        )
        self.phase_label.grid(row=0, column=0, padx=16, pady=(14, 4), sticky="w")
        self.status_label = ctk.CTkLabel(
            progress,
            text="Photos are copied into Person_001, Person_002, … and Grupo. Originals stay in place.",
            anchor="w",
            wraplength=620,
        )
        self.status_label.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")
        self.progress = ctk.CTkProgressBar(progress, progress_color=ACCENT)
        self.progress.grid(row=2, column=0, padx=16, pady=(0, 8), sticky="ew")
        self.progress.set(0)
        self.log_box = ctk.CTkTextbox(
            progress, font=ctk.CTkFont(family="Menlo", size=12)
        )
        self.log_box.grid(row=3, column=0, padx=16, pady=(0, 16), sticky="nsew")
        progress.grid_rowconfigure(3, weight=1)

    def _sort_config(self) -> SortConfig:
        return SortConfig(
            input_dir=self.input_dir.path,
            output_dir=self.output_dir.path,
            tolerance=MATCH_TOLERANCE,
            group_settings=GroupPhotoSettings(
                mode=GroupPhotoMode.ALL_FACES,
                group_output_folder=GROUP_OUTPUT_FOLDER,
            ),
        )

    def _persist_settings(self) -> None:
        save_settings(
            {
                "input_dir": str(self.input_dir.path),
                "output_dir": str(self.output_dir.path),
            }
        )

    def _set_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        self.sort_btn.configure(state=state)
        self.input_dir.entry.configure(state=state)
        self.output_dir.entry.configure(state=state)
        self.cancel_btn.configure(state="normal" if running else "disabled")

    def _request_cancel(self) -> None:
        self._cancel_event.set()

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
        self.progress.set(min(current / total if total else 0, 1.0))
        self.phase_label.configure(text="Sorting photos")
        self.status_label.configure(text=f"{message}  ({current}/{total})")

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

        self._persist_settings()
        self._cancel_event.clear()
        self._set_running(True)
        self.progress.set(0)
        self.log_box.delete("1.0", "end")
        config = self._sort_config()
        self._worker = threading.Thread(
            target=self._worker_run, args=(config,), daemon=True
        )
        self._worker.start()

    def _worker_run(self, config: SortConfig) -> None:
        try:
            result = run_sort(
                config,
                on_progress=self._on_progress,
                should_cancel=lambda: self._cancel_event.is_set(),
            )
            self._run_on_ui(self._finish, result)
        except Exception as exc:  # noqa: BLE001
            self._run_on_ui(self._finish_error, str(exc))

    def _finish(self, result: object) -> None:
        self._append_log(f"Output: {result.output_dir}")
        self._append_log(f"Person clusters: {result.num_clusters}")
        self._append_log(
            f"Copies: {result.matched_count} matched, {result.unmatched_count} unmatched"
        )
        if result.log_path:
            self._append_log(f"Log: {result.log_path}")
        for item in result.results[:30]:
            self._append_log(format_result_line(item))
        self._set_running(False)
        self.phase_label.configure(text="Done")
        self.status_label.configure(
            text="Sorting finished. Original photos in the input folder were not changed."
        )

    def _finish_error(self, message: str) -> None:
        self._append_log(f"ERROR: {message}")
        self._set_running(False)
        messagebox.showerror(APP_TITLE, message)


def main() -> None:
    ensure_app_support()
    app = EliseusSorterApp()
    app.mainloop()


if __name__ == "__main__":
    main()

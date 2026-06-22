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
    from production import SortConfig

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import customtkinter as ctk

from app_paths import ensure_app_support, is_app_bundle, load_settings, save_settings
from branding import ACCENT_COLOR, ACCENT_HOVER, APP_NAME
from config import (
    DEFAULT_FACE_SENSITIVITY,
    DEFAULT_INFERENCE_DEVICE,
    DEFAULT_MIN_CLASS_FACES,
    DEFAULT_MOVE_FILES,
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
from resource_monitor import format_duration, format_memory, snapshot_process_tree
from sort_runtime import SortCancelled
from ui_locale import (
    DEFAULT_LANGUAGE,
    LANGUAGE_BY_CODE,
    LANGUAGE_BY_LABEL,
    LANGUAGE_CHOICES,
    LANGUAGE_LABELS,
    Locale,
    format_resource_line_localized,
    friendly_step_detail,
    get_locale,
    inference_menu,
    worker_label_for_count,
    worker_labels,
    worker_value_from_label,
)

APP_TITLE = APP_NAME
WINDOW_SIZE = "720x900"
ACCENT = ACCENT_COLOR
ACCENT_HOVER = ACCENT_HOVER
MUTED = ("gray45", "gray60")
STEP_DONE = "#40916C"
STEP_ACTIVE = ACCENT
STEP_PENDING = ("gray78", "gray35")

PHASE_WEIGHTS_WITH_NAMING: dict[str, float] = {
    "scan": 0.50,
    "cluster": 0.12,
    "naming": 0.14,
    "naming_match": 0.09,
    "sort": 0.15,
}
PHASE_WEIGHTS_NO_NAMING: dict[str, float] = {
    "scan": 0.58,
    "cluster": 0.17,
    "sort": 0.25,
}


def _phase_order(has_naming_ref: bool) -> list[str]:
    if has_naming_ref:
        return ["scan", "cluster", "naming", "naming_match", "sort"]
    return ["scan", "cluster", "sort"]


def _phase_weights(has_naming_ref: bool) -> dict[str, float]:
    return PHASE_WEIGHTS_WITH_NAMING if has_naming_ref else PHASE_WEIGHTS_NO_NAMING


def _overall_progress(
    phase: str,
    current: int,
    total: int,
    *,
    has_naming_ref: bool,
) -> float:
    order = _phase_order(has_naming_ref)
    weights = _phase_weights(has_naming_ref)
    if phase not in order:
        return 0.0
    step_index = order.index(phase)
    completed = sum(weights.get(key, 0.0) for key in order[:step_index])
    step_weight = weights.get(phase, 0.1)
    inner = min(current / total, 1.0) if total else 0.0
    return min(completed + step_weight * inner, 1.0)


class StepIndicator(ctk.CTkFrame):
    """Single pipeline step — circle + title."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        number: int,
        title: str,
        **kwargs: object,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._number = number
        self._title = title
        self._badge = ctk.CTkLabel(
            self,
            text=str(number),
            width=28,
            height=28,
            corner_radius=14,
            fg_color=STEP_PENDING,
            text_color=("gray20", "gray90"),
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self._badge.pack(pady=(0, 4))
        self._label = ctk.CTkLabel(
            self,
            text=title,
            font=ctk.CTkFont(size=11),
            text_color=MUTED,
            wraplength=88,
            justify="center",
        )
        self._label.pack()
        self.set_state("pending")

    def set_title(self, title: str) -> None:
        self._title = title
        self._label.configure(text=title)

    def set_state(self, state: str) -> None:
        if state == "done":
            self._badge.configure(
                text="✓",
                fg_color=STEP_DONE,
                text_color="white",
            )
            self._label.configure(text_color=STEP_DONE, font=ctk.CTkFont(size=11, weight="bold"))
        elif state == "active":
            self._badge.configure(
                text=str(self._number),
                fg_color=STEP_ACTIVE,
                text_color="white",
            )
            self._label.configure(text_color=("gray10", "gray95"), font=ctk.CTkFont(size=11, weight="bold"))
        else:
            self._badge.configure(
                text=str(self._number),
                fg_color=STEP_PENDING,
                text_color=("gray35", "gray70"),
            )
            self._label.configure(text_color=MUTED, font=ctk.CTkFont(size=11))


class SortProgressPanel(ctk.CTkFrame):
    """Step pipeline, overall bar, and plain-language status."""

    def __init__(self, master: ctk.CTkBaseClass, locale: Locale, **kwargs: object) -> None:
        super().__init__(master, corner_radius=12, **kwargs)
        self._locale = locale
        self.grid_columnconfigure(0, weight=1)
        self._has_naming_ref = False
        self._move_files = False
        self._step_widgets: dict[str, StepIndicator] = {}
        self._step_keys: list[str] = []

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        self.headline = ctk.CTkLabel(
            header,
            text=locale.t("ready_to_sort"),
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        )
        self.headline.grid(row=0, column=0, sticky="w")
        self.percent_label = ctk.CTkLabel(
            header,
            text="",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=ACCENT,
        )
        self.percent_label.grid(row=0, column=1, sticky="e")

        self.steps_row = ctk.CTkFrame(self, fg_color="transparent")
        self.steps_row.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")

        self.step_caption = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=13),
            text_color=("gray25", "gray80"),
            anchor="w",
            wraplength=640,
            justify="left",
        )
        self.step_caption.grid(row=2, column=0, padx=16, pady=(0, 4), sticky="ew")

        self.detail_label = ctk.CTkLabel(
            self,
            text=locale.t("ready_hint"),
            font=ctk.CTkFont(size=12),
            text_color=MUTED,
            anchor="w",
            wraplength=640,
            justify="left",
        )
        self.detail_label.grid(row=3, column=0, padx=16, pady=(0, 10), sticky="ew")

        self.progress = ctk.CTkProgressBar(self, height=14, progress_color=ACCENT, corner_radius=7)
        self.progress.grid(row=4, column=0, padx=16, pady=(0, 8), sticky="ew")
        self.progress.set(0)

        self.resource_label = ctk.CTkLabel(
            self,
            text="",
            anchor="w",
            font=ctk.CTkFont(size=11),
            text_color=MUTED,
        )
        self.resource_label.grid(row=5, column=0, padx=16, pady=(0, 6), sticky="ew")

        log_header = ctk.CTkFrame(self, fg_color="transparent")
        log_header.grid(row=6, column=0, padx=16, pady=(4, 4), sticky="ew")
        self._log_title = ctk.CTkLabel(
            log_header,
            text=locale.t("activity_log"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=MUTED,
            anchor="w",
        )
        self._log_title.pack(side="left")

        self.log_box = ctk.CTkTextbox(self, font=ctk.CTkFont(size=12), height=140)
        self.log_box.grid(row=7, column=0, padx=16, pady=(0, 16), sticky="nsew")
        self.grid_rowconfigure(7, weight=1)

        self._build_step_row(_phase_order(False))

    def set_locale(self, locale: Locale) -> None:
        self._locale = locale
        self._log_title.configure(text=locale.t("activity_log"))
        self.set_idle()

    def _step_title(self, key: str) -> str:
        title, _ = self._locale.pipeline_step(key)
        if key == "sort" and self._move_files:
            return self._locale.t("step_move_photos")
        return title

    def _build_step_row(self, step_keys: list[str]) -> None:
        for widget in self.steps_row.winfo_children():
            widget.destroy()
        self._step_widgets.clear()
        self._step_keys = step_keys
        for index, key in enumerate(step_keys, start=1):
            widget = StepIndicator(self.steps_row, number=index, title=self._step_title(key))
            widget.pack(side="left", expand=True, fill="x", padx=4)
            self._step_widgets[key] = widget

    def configure_pipeline(self, has_naming_ref: bool) -> None:
        self._has_naming_ref = has_naming_ref
        keys = _phase_order(has_naming_ref)
        if keys != self._step_keys:
            self._build_step_row(keys)

    def reset(self) -> None:
        loc = self._locale
        self.headline.configure(text=loc.t("preparing"))
        self.percent_label.configure(text="0%")
        self.step_caption.configure(text=loc.t("preparing_caption"))
        self.detail_label.configure(text=loc.t("preparing_detail"))
        self.progress.set(0)
        for key in self._step_keys:
            self._step_widgets[key].set_state("pending")

    def set_complete(self, *, message: str) -> None:
        loc = self._locale
        self.headline.configure(text=loc.t("complete"))
        self.percent_label.configure(text="100%")
        self.progress.set(1.0)
        self.step_caption.configure(text=message)
        self.detail_label.configure(text=loc.t("complete_detail"))
        for key in self._step_keys:
            self._step_widgets[key].set_state("done")

    def set_idle(self) -> None:
        loc = self._locale
        self.headline.configure(text=loc.t("ready_to_sort"))
        self.percent_label.configure(text="")
        self.step_caption.configure(text="")
        self.detail_label.configure(text=loc.t("ready_hint"))
        self.progress.set(0)
        self.resource_label.configure(text="")
        for key in self._step_keys:
            self._step_widgets[key].set_state("pending")
        self._refresh_step_titles()

    def _refresh_step_titles(self) -> None:
        for key, widget in self._step_widgets.items():
            widget.set_title(self._step_title(key))

    def update_phase(self, phase: str, current: int, total: int, message: str) -> None:
        loc = self._locale
        title, caption = loc.pipeline_step(phase)
        if phase == "sort" and self._move_files:
            title = loc.t("step_move_photos")

        order = _phase_order(self._has_naming_ref)
        if phase in order:
            active_index = order.index(phase)
            for index, key in enumerate(order):
                if index < active_index:
                    self._step_widgets[key].set_state("done")
                elif index == active_index:
                    self._step_widgets[key].set_state("active")
                else:
                    self._step_widgets[key].set_state("pending")

        fraction = _overall_progress(
            phase, current, total, has_naming_ref=self._has_naming_ref
        )
        percent = int(fraction * 100)
        self.progress.set(fraction)
        self.percent_label.configure(text=f"{percent}%")
        self.headline.configure(text=title)
        self.step_caption.configure(text=caption)
        self.detail_label.configure(
            text=friendly_step_detail(loc, phase, message, current, total)
        )

    def set_move_mode(self, move_files: bool) -> None:
        self._move_files = move_files
        self._refresh_step_titles()


def _inference_device_menu_choices(locale: Locale) -> tuple[list[str], dict[str, str], dict[str, str]]:
    return inference_menu(locale, available_accelerators())


class PathSelector(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTkBaseClass,
        label_key: str,
        locale: Locale,
        initial: Path | str = "",
        **kwargs: object,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._label_key = label_key
        self._locale = locale
        self.grid_columnconfigure(1, weight=1)
        self._path_label = ctk.CTkLabel(self, text=locale.t(label_key), width=120, anchor="w")
        self._path_label.grid(row=0, column=0, padx=(0, 8), sticky="w")
        self._var = tk.StringVar(value=str(initial))
        self.entry = ctk.CTkEntry(self, textvariable=self._var)
        self.entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self._browse_btn = ctk.CTkButton(
            self,
            text=locale.t("browse"),
            width=90,
            command=self._browse,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
        )
        self._browse_btn.grid(row=0, column=2)

    def set_locale(self, locale: Locale) -> None:
        self._locale = locale
        self._path_label.configure(text=locale.t(self._label_key))
        self._browse_btn.configure(text=locale.t("browse"))

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(
            title=self._locale.t("folder_dialog_title"),
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
        self._locale = get_locale(self._settings.get("language", DEFAULT_LANGUAGE))
        self._inference_device_value = DEFAULT_INFERENCE_DEVICE
        self._scan_worker_count = DEFAULT_SCAN_WORKERS
        self._cancel_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._monitor_stop = threading.Event()
        self._sort_started_at: Optional[float] = None
        self._active_scan_workers = DEFAULT_SCAN_WORKERS
        self._last_progress_phase: Optional[str] = None
        self._ui_queue: queue.Queue = queue.Queue()

        self._build_layout()
        self._apply_language()
        self._poll_ui_queue()

    def _apply_language(self) -> None:
        loc = self._locale
        self.tagline_label.configure(text=loc.t("tagline"))
        self.input_dir.set_locale(loc)
        self.output_dir.set_locale(loc)
        self.naming_reference_dir.set_locale(loc)
        self.ref_skip_label.configure(text=loc.t("label_ref_skip"))
        self.ref_skip_hint.configure(text=loc.t("hint_ref_skip"))
        self.group_faces_label.configure(text=loc.t("label_group_faces"))
        self.group_faces_hint.configure(text=loc.t("hint_group_faces"))
        self.move_files_checkbox.configure(text=loc.t("move_files"))
        self.duplicate_group_checkbox.configure(text=loc.t("duplicate_group"))
        self.bg_sensitivity_label.configure(text=loc.t("label_bg_sensitivity"))
        self.workers_label.configure(text=loc.t("label_scan_workers"))
        self.workers_hint.configure(text=loc.t("hint_scan_workers"))
        self.accel_label.configure(text=loc.t("label_acceleration"))
        self._refresh_accel_hint()
        self.sort_btn.configure(text=loc.t("btn_sort"))
        self.cancel_btn.configure(text=loc.t("btn_cancel"))
        self.progress_panel.set_locale(loc)
        self._refresh_worker_menu()
        self._refresh_inference_menu()
        self._update_face_sensitivity_label(self.face_sensitivity_var.get())

    def _refresh_accel_hint(self) -> None:
        loc = self._locale
        if available_accelerators()["coreml"]:
            hint = loc.t("accel_hint_coreml")
        elif available_accelerators()["cuda"]:
            hint = loc.t("accel_hint_cuda")
        else:
            hint = loc.t("accel_hint_cpu")
        self.accel_hint.configure(text=hint)

    def _refresh_worker_menu(self) -> None:
        loc = self._locale
        labels = worker_labels(loc)
        self.scan_workers_menu.configure(values=labels)
        self.scan_workers_var.set(worker_label_for_count(loc, self._scan_worker_count))

    def _refresh_inference_menu(self) -> None:
        loc = self._locale
        labels, label_to_value, value_to_label = _inference_device_menu_choices(loc)
        self.inference_device_labels = labels
        self.inference_device_values = label_to_value
        self.inference_device_by_value = value_to_label
        self.inference_device_menu.configure(values=labels)
        self.inference_device_var.set(value_to_label.get(self._inference_device_value, labels[0]))

    def _on_language_changed(self, choice: str) -> None:
        code = LANGUAGE_BY_LABEL.get(choice, DEFAULT_LANGUAGE)
        self._locale = get_locale(code)
        self._apply_language()
        if not (self._worker and self._worker.is_alive()):
            self._persist_settings()

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, corner_radius=12)
        header.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header, text=APP_TITLE, font=ctk.CTkFont(size=26, weight="bold")
        ).grid(row=0, column=0, padx=20, pady=(16, 4), sticky="w")
        self.tagline_label = ctk.CTkLabel(
            header,
            text="",
            font=ctk.CTkFont(size=13),
            text_color=("gray30", "gray70"),
            wraplength=520,
            justify="left",
        )
        self.tagline_label.grid(row=1, column=0, padx=20, pady=(0, 16), sticky="w")

        lang_code = self._settings.get("language", DEFAULT_LANGUAGE)
        lang_label = LANGUAGE_BY_CODE.get(lang_code, LANGUAGE_LABELS[0])
        self.language_var = tk.StringVar(value=lang_label)
        self.language_menu = ctk.CTkOptionMenu(
            header,
            variable=self.language_var,
            values=LANGUAGE_LABELS,
            width=130,
            command=self._on_language_changed,
        )
        self.language_menu.grid(row=0, column=1, rowspan=2, padx=20, pady=16, sticky="ne")

        paths = ctk.CTkFrame(self, corner_radius=12)
        paths.grid(row=1, column=0, padx=20, pady=8, sticky="ew")
        paths.grid_columnconfigure(0, weight=1)
        loc = self._locale
        self.input_dir = PathSelector(
            paths, "label_input", loc, self._settings.get("input_dir", "")
        )
        self.input_dir.grid(row=0, column=0, padx=16, pady=(16, 6), sticky="ew")
        self.output_dir = PathSelector(
            paths, "label_output", loc, self._settings.get("output_dir", "")
        )
        self.output_dir.grid(row=1, column=0, padx=16, pady=(6, 6), sticky="ew")
        self.naming_reference_dir = PathSelector(
            paths,
            "label_naming_ref",
            loc,
            self._settings.get("naming_reference", ""),
        )
        self.naming_reference_dir.grid(row=2, column=0, padx=16, pady=(6, 6), sticky="ew")

        naming_skip_row = ctk.CTkFrame(paths, fg_color="transparent")
        naming_skip_row.grid(row=3, column=0, padx=16, pady=(0, 6), sticky="ew")
        self.ref_skip_label = ctk.CTkLabel(naming_skip_row, text="", width=120, anchor="w")
        self.ref_skip_label.grid(row=0, column=0, sticky="w")
        self.naming_reference_skip_var = tk.StringVar(
            value=str(
                self._settings.get("naming_reference_skip", DEFAULT_NAMING_REFERENCE_SKIP)
            )
        )
        self.naming_reference_skip_entry = ctk.CTkEntry(
            naming_skip_row, textvariable=self.naming_reference_skip_var, width=80
        )
        self.naming_reference_skip_entry.grid(row=0, column=1, sticky="w", padx=(0, 8))
        self.ref_skip_hint = ctk.CTkLabel(
            naming_skip_row,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
        )
        self.ref_skip_hint.grid(row=0, column=2, sticky="w")

        class_row = ctk.CTkFrame(paths, fg_color="transparent")
        class_row.grid(row=4, column=0, padx=16, pady=(0, 6), sticky="ew")
        self.group_faces_label = ctk.CTkLabel(class_row, text="", width=120, anchor="w")
        self.group_faces_label.grid(row=0, column=0, sticky="w")
        self.min_class_faces_var = tk.StringVar(
            value=str(self._settings.get("min_class_faces", DEFAULT_MIN_CLASS_FACES))
        )
        ctk.CTkEntry(class_row, textvariable=self.min_class_faces_var, width=80).grid(
            row=0, column=1, sticky="w", padx=(0, 8)
        )
        self.group_faces_hint = ctk.CTkLabel(
            class_row,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
        )
        self.group_faces_hint.grid(row=0, column=2, sticky="w")

        transfer_row = ctk.CTkFrame(paths, fg_color="transparent")
        transfer_row.grid(row=5, column=0, padx=16, pady=(0, 6), sticky="ew")
        self.move_files_var = tk.BooleanVar(
            value=bool(self._settings.get("move_files", DEFAULT_MOVE_FILES))
        )
        self.move_files_checkbox = ctk.CTkCheckBox(
            transfer_row,
            text="",
            variable=self.move_files_var,
        )
        self.move_files_checkbox.grid(row=0, column=0, sticky="w")

        options_row = ctk.CTkFrame(paths, fg_color="transparent")
        options_row.grid(row=6, column=0, padx=16, pady=(0, 6), sticky="ew")
        self.duplicate_group_photos_var = tk.BooleanVar(
            value=bool(self._settings.get("duplicate_group_photos", False))
        )
        self.duplicate_group_checkbox = ctk.CTkCheckBox(
            options_row,
            text="",
            variable=self.duplicate_group_photos_var,
        )
        self.duplicate_group_checkbox.grid(row=0, column=0, sticky="w")

        sensitivity_row = ctk.CTkFrame(paths, fg_color="transparent")
        sensitivity_row.grid(row=7, column=0, padx=16, pady=(0, 6), sticky="ew")
        sensitivity_row.grid_columnconfigure(1, weight=1)
        self.bg_sensitivity_label = ctk.CTkLabel(
            sensitivity_row, text="", width=160, anchor="w"
        )
        self.bg_sensitivity_label.grid(row=0, column=0, sticky="w")
        saved_sensitivity = int(
            self._settings.get("face_sensitivity", DEFAULT_FACE_SENSITIVITY)
        )
        saved_sensitivity = max(0, min(100, saved_sensitivity))
        self.face_sensitivity_var = tk.IntVar(value=saved_sensitivity)
        self.face_sensitivity_slider = ctk.CTkSlider(
            sensitivity_row,
            from_=0,
            to=100,
            number_of_steps=100,
            variable=self.face_sensitivity_var,
            command=self._update_face_sensitivity_label,
        )
        self.face_sensitivity_slider.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.face_sensitivity_label = ctk.CTkLabel(
            sensitivity_row,
            text="",
            width=180,
            anchor="w",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
        )
        self.face_sensitivity_label.grid(row=0, column=2, sticky="w")
        self._update_face_sensitivity_label(saved_sensitivity)

        workers_row = ctk.CTkFrame(paths, fg_color="transparent")
        workers_row.grid(row=8, column=0, padx=16, pady=(0, 6), sticky="ew")
        self.workers_label = ctk.CTkLabel(workers_row, text="", width=120, anchor="w")
        self.workers_label.grid(row=0, column=0, sticky="w")
        saved_workers = int(self._settings.get("scan_workers", DEFAULT_SCAN_WORKERS))
        saved_workers = max(1, saved_workers)
        self._scan_worker_count = saved_workers
        default_label = worker_label_for_count(loc, saved_workers)
        custom_workers = "" if saved_workers in {1, 2, 3, 4, 5, 6, 7, 8} else str(saved_workers)
        self.scan_workers_var = tk.StringVar(value=default_label)
        self.scan_workers_menu = ctk.CTkOptionMenu(
            workers_row,
            variable=self.scan_workers_var,
            values=worker_labels(loc),
            width=180,
            command=self._on_scan_workers_menu_changed,
        )
        self.scan_workers_menu.grid(row=0, column=1, sticky="w", padx=(0, 8))
        self.scan_workers_custom_var = tk.StringVar(value=custom_workers)
        self.scan_workers_custom_entry = ctk.CTkEntry(
            workers_row,
            textvariable=self.scan_workers_custom_var,
            width=56,
            placeholder_text="N",
        )
        self.scan_workers_custom_entry.grid(row=0, column=2, sticky="w", padx=(0, 8))
        self._on_scan_workers_menu_changed(default_label)
        self.workers_hint = ctk.CTkLabel(
            workers_row,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
        )
        self.workers_hint.grid(row=0, column=3, sticky="w")

        accel_row = ctk.CTkFrame(paths, fg_color="transparent")
        accel_row.grid(row=9, column=0, padx=16, pady=(0, 6), sticky="ew")
        self.accel_label = ctk.CTkLabel(accel_row, text="", width=120, anchor="w")
        self.accel_label.grid(row=0, column=0, sticky="w")
        (
            self.inference_device_labels,
            self.inference_device_values,
            self.inference_device_by_value,
        ) = _inference_device_menu_choices(loc)
        saved_device = str(
            self._settings.get("inference_device", DEFAULT_INFERENCE_DEVICE)
        ).lower()
        if saved_device not in self.inference_device_by_value:
            saved_device = DEFAULT_INFERENCE_DEVICE
        self._inference_device_value = saved_device
        self.inference_device_var = tk.StringVar(
            value=self.inference_device_by_value.get(saved_device, self.inference_device_labels[0])
        )
        self.inference_device_menu = ctk.CTkOptionMenu(
            accel_row,
            variable=self.inference_device_var,
            values=self.inference_device_labels,
            width=180,
            command=self._on_inference_device_changed,
        )
        self.inference_device_menu.grid(row=0, column=1, sticky="w", padx=(0, 8))
        self.accel_hint = ctk.CTkLabel(
            accel_row,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
        )
        self.accel_hint.grid(row=0, column=2, sticky="w")

        actions = ctk.CTkFrame(paths, fg_color="transparent")
        actions.grid(row=10, column=0, padx=16, pady=(0, 16), sticky="ew")
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(1, weight=1)
        self.sort_btn = ctk.CTkButton(
            actions,
            text="",
            command=self._start_sort,
            fg_color="#1B4332",
            hover_color=ACCENT,
        )
        self.sort_btn.grid(row=0, column=0, padx=(0, 4), sticky="ew")
        self.cancel_btn = ctk.CTkButton(
            actions,
            text="",
            command=self._request_cancel,
            state="disabled",
            fg_color="#6C757D",
        )
        self.cancel_btn.grid(row=0, column=1, padx=(4, 0), sticky="ew")

        progress = SortProgressPanel(self, self._locale)
        progress.grid(row=2, column=0, padx=20, pady=(8, 20), sticky="nsew")
        self.progress_panel = progress
        self.progress = progress.progress
        self.phase_label = progress.headline
        self.status_label = progress.step_caption
        self.resource_label = progress.resource_label
        self.log_box = progress.log_box
        self.grid_rowconfigure(2, weight=1)

    def _min_class_faces(self) -> int:
        try:
            value = int(self.min_class_faces_var.get().strip())
        except ValueError as exc:
            raise ValueError(self._locale.t("error_group_faces_int")) from exc
        if value < 1:
            raise ValueError(self._locale.t("error_group_faces_min"))
        return value

    def _naming_reference_skip(self) -> int:
        try:
            value = int(self.naming_reference_skip_var.get().strip())
        except ValueError as exc:
            raise ValueError(self._locale.t("error_ref_skip_int")) from exc
        if value < 0:
            raise ValueError(self._locale.t("error_ref_skip_min"))
        return value

    def _update_face_sensitivity_label(self, value: float | str = 0) -> None:
        level = int(float(value))
        loc = self._locale
        if level <= 33:
            hint = loc.t("sensitivity_strict")
        elif level >= 67:
            hint = loc.t("sensitivity_permissive")
        else:
            hint = loc.t("sensitivity_balanced")
        self.face_sensitivity_label.configure(text=f"{level} · {hint}")

    def _on_scan_workers_menu_changed(self, choice: str) -> None:
        self._scan_worker_count = worker_value_from_label(self._locale, choice)
        is_custom = self._scan_worker_count < 0
        state = "normal" if is_custom else "disabled"
        self.scan_workers_custom_entry.configure(state=state)

    def _on_inference_device_changed(self, choice: str) -> None:
        self._inference_device_value = self.inference_device_values.get(
            choice, DEFAULT_INFERENCE_DEVICE
        )

    def _face_sensitivity(self) -> int:
        return max(0, min(100, int(self.face_sensitivity_var.get())))

    def _scan_workers(self) -> int:
        label = self.scan_workers_var.get()
        preset = worker_value_from_label(self._locale, label)
        if preset >= 1:
            return preset
        try:
            value = int(self.scan_workers_custom_var.get().strip())
        except ValueError as exc:
            raise ValueError(self._locale.t("error_workers_int")) from exc
        if value < 1:
            raise ValueError(self._locale.t("error_workers_min"))
        return value

    def _inference_device(self) -> str:
        return self._inference_device_value

    def _naming_reference_path(self) -> Optional[Path]:
        raw = self.naming_reference_dir.path
        if not str(raw).strip():
            return None
        if not raw.is_dir():
            raise ValueError(self._locale.t("error_naming_ref"))
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
            move_files=self.move_files_var.get(),
            face_sensitivity=self._face_sensitivity(),
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
                "move_files": self.move_files_var.get(),
                "face_sensitivity": self._face_sensitivity(),
                "scan_workers": self._scan_workers(),
                "inference_device": self._inference_device(),
                "language": self._locale.code,
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
        self.move_files_checkbox.configure(state=state)
        self.face_sensitivity_slider.configure(state=state)
        self.scan_workers_menu.configure(state=state)
        if self.scan_workers_var.get() == self._locale.t("worker_custom"):
            self.scan_workers_custom_entry.configure(state=state)
        else:
            self.scan_workers_custom_entry.configure(state="disabled")
        self.inference_device_menu.configure(state=state)
        self.language_menu.configure(state=state)
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
        if phase != self._last_progress_phase:
            title, _ = self._locale.pipeline_step(phase)
            if phase == "sort" and getattr(self.progress_panel, "_move_files", False):
                title = self._locale.t("step_move_photos")
            self._append_log(f"▸ {title}")
            self._last_progress_phase = phase
        self.progress_panel.update_phase(phase, current, total, message)

    def _update_resources(self) -> None:
        if self._sort_started_at is None:
            return
        elapsed = time.perf_counter() - self._sort_started_at
        snap = snapshot_process_tree()
        self.resource_label.configure(
            text=format_resource_line_localized(
                self._locale,
                memory_mb=snap.memory_mb,
                cpu_percent=snap.cpu_percent,
                scan_workers=self._active_scan_workers,
                elapsed_seconds=elapsed,
                inference=active_inference_label(),
                process_count=snap.process_count,
                format_memory=format_memory,
                format_duration=format_duration,
            )
        )

    def _start_sort(self) -> None:
        loc = self._locale
        if self._worker and self._worker.is_alive():
            messagebox.showwarning(APP_TITLE, loc.t("error_already_running"))
            return
        if not self.input_dir.path.is_dir():
            messagebox.showerror(APP_TITLE, loc.t("error_input_missing"))
            return
        if not self.output_dir.path:
            messagebox.showerror(APP_TITLE, loc.t("error_output_missing"))
            return

        try:
            config = self._sort_config()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        device = self._inference_device()
        configure_inference_device(device)

        self._persist_settings()
        self._cancel_event.clear()
        self._monitor_stop.clear()
        self._sort_started_at = time.perf_counter()
        self._active_scan_workers = config.scan_workers
        self._active_move_files = config.move_files
        has_naming = config.naming_reference is not None
        self.progress_panel.configure_pipeline(has_naming)
        self.progress_panel.set_move_mode(config.move_files)
        self.progress_panel.reset()
        self._last_progress_phase = None
        self._set_running(True)
        self.resource_label.configure(
            text=loc.t("loading_models", device=active_inference_label())
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
        except SortCancelled:
            self._run_on_ui(self._finish_cancelled)
        except Exception as exc:  # noqa: BLE001
            self._run_on_ui(self._finish_error, str(exc))
        finally:
            self._monitor_stop.set()

    def _format_runtime(self, runtime: object) -> str:
        return self._locale.t(
            "log_timing",
            scan=runtime.scan_seconds,
            cluster=runtime.cluster_seconds,
            copy=runtime.copy_seconds,
            faces=runtime.num_faces_detected,
            with_face=runtime.num_images_with_face,
            images=runtime.num_images,
        )

    def _log_result(self, result: object) -> None:
        loc = self._locale
        self._append_log(loc.t("log_output", path=result.output_dir))
        if result.num_classes:
            self._append_log(loc.t("log_roster_groups", count=result.num_classes))
        self._append_log(loc.t("log_person_clusters", count=result.num_clusters))
        if getattr(self, "_active_move_files", False):
            self._append_log(
                loc.t(
                    "log_moves",
                    matched=result.matched_count,
                    unmatched=result.unmatched_count,
                )
            )
        else:
            self._append_log(
                loc.t(
                    "log_copies",
                    matched=result.matched_count,
                    unmatched=result.unmatched_count,
                )
            )
        if result.log_path:
            self._append_log(loc.t("log_file", path=result.log_path))
        if getattr(result, "runtime", None):
            self._append_log(self._format_runtime(result.runtime))
        if result.person_renames:
            self._append_log(loc.t("log_person_names"))
            for generic, named in sorted(result.person_renames.items()):
                self._append_log(f"  {generic} → {named}")

    def _finish(self, outcome: object) -> None:
        move_files = getattr(self, "_active_move_files", False)
        self._log_result(outcome)
        for item in outcome.results[:30]:
            self._append_log(format_result_line(item))

        self._set_running(False)
        self._sort_started_at = None
        finish_text = (
            self._locale.t("finish_moved")
            if move_files
            else self._locale.t("finish_copied")
        )
        self.progress_panel.set_complete(message=finish_text)
        self._update_resources()

    def _finish_cancelled(self) -> None:
        loc = self._locale
        self._append_log(loc.t("sort_cancelled"))
        self._set_running(False)
        self._sort_started_at = None
        self.progress_panel.headline.configure(text=loc.t("sort_cancelled"))
        self.progress_panel.percent_label.configure(text="")
        self.progress_panel.step_caption.configure(text=loc.t("sort_cancelled_detail"))
        self.progress_panel.detail_label.configure(text="")
        self.resource_label.configure(text="")

    def _finish_error(self, message: str) -> None:
        loc = self._locale
        self._append_log(f"ERROR: {message}")
        self._set_running(False)
        self._sort_started_at = None
        self.progress_panel.headline.configure(text=loc.t("error_headline"))
        self.progress_panel.percent_label.configure(text="")
        self.progress_panel.step_caption.configure(text=loc.t("error_caption"))
        self.progress_panel.detail_label.configure(text=message)
        self.resource_label.configure(text="")
        messagebox.showerror(APP_TITLE, message)


def main() -> None:
    ensure_app_support()
    app = EliseusSorterApp()
    app.mainloop()


if __name__ == "__main__":
    main()

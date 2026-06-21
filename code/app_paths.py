"""Application install location vs user data (photos, output)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def is_app_bundle() -> bool:
    return os.environ.get("ELISEUS_SORTER_APP") == "1"


def project_root() -> Path:
    if is_app_bundle():
        return Path(os.environ["ELISEUS_RESOURCES"])
    return Path(__file__).resolve().parent.parent


def app_support_dir() -> Path:
    """App-only files: venv, reference DB, settings, logs. Never user photos."""
    return Path.home() / "Library/Application Support/Eliseus Sorter"


def default_reference_db() -> Path:
    return app_support_dir() / "reference.db"


def settings_path() -> Path:
    return app_support_dir() / "settings.json"


def benchmark_data_dir() -> Path:
    """Developer benchmarking datasets (not used by the production app)."""
    return project_root() / "data" / "benchmark"


def results_dir() -> Path:
    """Generated reports and benchmark outputs (never committed)."""
    return project_root() / "results"


def load_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(settings: dict[str, Any]) -> None:
    app_support_dir().mkdir(parents=True, exist_ok=True)
    settings_path().write_text(json.dumps(settings, indent=2), encoding="utf-8")


def ensure_app_support() -> None:
    app_support_dir().mkdir(parents=True, exist_ok=True)
    (app_support_dir() / "logs").mkdir(parents=True, exist_ok=True)

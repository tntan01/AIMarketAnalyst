from __future__ import annotations

import os
from pathlib import Path

from config.constants import APP_ID

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
ASSETS_DIR = PROJECT_ROOT / "assets"


def app_data_dir() -> Path:
    base = os.getenv("APPDATA")
    if base:
        return Path(base) / APP_ID
    return Path.home() / f".{APP_ID}"


def ensure_runtime_dirs() -> None:
    for path in [app_data_dir(), app_data_dir() / "logs", app_data_dir() / "cache"]:
        path.mkdir(parents=True, exist_ok=True)


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def journal_db_path() -> Path:
    return app_data_dir() / "journal.db"


def log_path() -> Path:
    return app_data_dir() / "logs" / "app.log"

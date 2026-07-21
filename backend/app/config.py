from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP_SUPPORT_NAME = "AutoPaperReader"


@dataclass(frozen=True)
class AppConfig:
    root_dir: Path
    report_dir: Path
    source_dir: Path
    db_path: Path
    openai_api_key: str
    openai_base_url: str


def load_config() -> AppConfig:
    root_dir = Path(os.environ.get("AUTOPAPER_ROOT", ROOT)).expanduser().resolve()
    data_dir = desktop_data_dir() if os.environ.get("AUTOPAPER_DESKTOP") == "1" else root_dir
    db_path = Path(os.environ.get("AUTOPAPER_DB_PATH", data_dir / "app.db")).expanduser()
    stored_paths = _read_path_settings(db_path)
    report_dir = Path(
        os.environ.get("AUTOPAPER_REPORT_DIR")
        or stored_paths.get("report_dir")
        or data_dir / "docs"
    ).expanduser()
    source_dir = Path(
        os.environ.get("AUTOPAPER_SOURCE_DIR")
        or stored_paths.get("source_dir")
        or data_dir / "sources"
    ).expanduser()
    return AppConfig(
        root_dir=root_dir,
        report_dir=report_dir.resolve(),
        source_dir=source_dir.resolve(),
        db_path=db_path.resolve(),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        openai_base_url=os.environ.get("AUTOPAPER_OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )


def desktop_data_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / APP_SUPPORT_NAME


def _read_path_settings(db_path: Path) -> dict[str, str]:
    if not db_path.exists():
        return {}
    try:
        with closing(sqlite3.connect(db_path)) as conn:
            rows = conn.execute(
                "SELECT key, value FROM settings WHERE key IN ('report_dir', 'source_dir')"
            ).fetchall()
    except sqlite3.Error:
        return {}
    return {str(key): str(value) for key, value in rows if str(value).strip()}

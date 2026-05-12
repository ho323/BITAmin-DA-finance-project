from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    database_url: str
    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    report_dir: Path = PROJECT_ROOT / "reports"
    event_config_path: Path = PROJECT_ROOT / "configs" / "events.yml"


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://bitamin:bitamin@localhost:5432/bitamin_finance",
    )
    return Settings(database_url=database_url)


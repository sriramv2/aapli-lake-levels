"""SQLite storage for daily lake readings and loading of static lake facts."""
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAKES_JSON = ROOT / "data" / "lakes.json"
DEFAULT_DB = ROOT / "data" / "aapli.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    date        TEXT    NOT NULL,   -- ISO date, reading taken at 06:00 IST
    lake_id     TEXT    NOT NULL,
    storage_ml  INTEGER NOT NULL,   -- live storage in million litres
    source      TEXT    NOT NULL,   -- 'simulated' or 'bmc'
    PRIMARY KEY (date, lake_id)
);
CREATE INDEX IF NOT EXISTS readings_lake_date ON readings (lake_id, date);

-- City-wide percent full for dates where per-lake readings are not available.
CREATE TABLE IF NOT EXISTS reference_totals (
    date    TEXT PRIMARY KEY,
    percent REAL NOT NULL,
    source  TEXT NOT NULL
);
"""


def db_path() -> Path:
    return Path(os.environ.get("AAPLI_DB", DEFAULT_DB))


def connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or db_path())
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def include_simulated() -> bool:
    """Simulated rows are hidden unless AAPLI_INCLUDE_SIMULATED=1 (dev only)."""
    return os.environ.get("AAPLI_INCLUDE_SIMULATED") == "1"


def load_lake_facts() -> dict:
    with open(LAKES_JSON, encoding="utf-8") as f:
        return json.load(f)

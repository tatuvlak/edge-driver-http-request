"""Storage for weather readings pushed by the ESP32 sensor.

The sensor posts a reading every 30 seconds. This keeps the latest one for the
displays to read, plus a rolling window of history — which is what replaces the
graphs lost by leaving SmartThings.

SQLite on the container's mounted /app/data volume, so readings survive restarts.
Connections are opened per call rather than shared: gunicorn runs multiple
workers, and a connection handed between them is a good way to get obscure
"database is locked" failures. WAL mode keeps concurrent readers off the
writer's back.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# The numeric fields a reading carries, with the range each must fall in to be
# believable. A sensor glitch that writes -400 °C should be rejected at the door
# rather than rendered on the TV.
FIELDS: dict[str, tuple[float, float]] = {
    "temperature_c": (-50.0, 80.0),
    "humidity_pct": (0.0, 100.0),
    "pressure_hpa": (800.0, 1200.0),
    "pm1": (0.0, 2000.0),
    "pm25": (0.0, 2000.0),
    "pm10": (0.0, 2000.0),
}

# Matter's AirQualityEnum: 0 unknown, 1 good … 6 extremely poor. The firmware
# already computes this, and dashboard.js already consumes exactly these values.
AQI_RANGE = (0, 6)

_COLUMNS = list(FIELDS) + ["aqi"]


class ValidationError(ValueError):
    """The posted reading was not usable."""


def _connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init(db_path: str) -> None:
    with _connect(db_path) as conn:
        columns = ", ".join(f"{name} REAL" for name in FIELDS)
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS readings (
                recorded_at REAL NOT NULL,
                {columns},
                aqi INTEGER
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_recorded_at ON readings(recorded_at)")
    logger.info("Weather store ready at %s", db_path)


def validate(payload: Any) -> dict:
    """Turn a posted body into a clean reading, or raise ValidationError.

    Every field is optional — the pressure sensor may be absent, and a PMS read
    can fail on any given cycle — but anything present must be a number within a
    plausible range. A reading with no usable field at all is rejected, since
    storing it would only push a good reading out of 'latest'.
    """
    if not isinstance(payload, dict):
        raise ValidationError("body must be a JSON object")

    reading: dict = {}

    for name, (low, high) in FIELDS.items():
        if name not in payload or payload[name] is None:
            continue
        value = payload[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError(f"{name} must be a number, got {type(value).__name__}")
        value = float(value)
        if value != value:  # NaN
            raise ValidationError(f"{name} is not a number")
        if not low <= value <= high:
            raise ValidationError(f"{name}={value} is outside the plausible range {low}..{high}")
        reading[name] = value

    if "aqi" in payload and payload["aqi"] is not None:
        aqi = payload["aqi"]
        if isinstance(aqi, bool) or not isinstance(aqi, int):
            raise ValidationError("aqi must be an integer 0-6")
        if not AQI_RANGE[0] <= aqi <= AQI_RANGE[1]:
            raise ValidationError(f"aqi={aqi} is outside {AQI_RANGE[0]}..{AQI_RANGE[1]}")
        reading["aqi"] = aqi

    if not reading:
        raise ValidationError("no usable fields in reading")

    return reading


def record(db_path: str, reading: dict, recorded_at: float | None = None) -> float:
    """Store a validated reading. Returns its timestamp."""
    recorded_at = time.time() if recorded_at is None else recorded_at
    columns = ["recorded_at"] + [c for c in _COLUMNS if c in reading]
    values = [recorded_at] + [reading[c] for c in _COLUMNS if c in reading]
    placeholders = ", ".join("?" * len(columns))
    with _connect(db_path) as conn:
        conn.execute(
            f"INSERT INTO readings ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
    return recorded_at


def latest(db_path: str) -> dict | None:
    """The most recent reading, or None if nothing has been recorded yet."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM readings ORDER BY recorded_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def history(db_path: str, hours: float = 24.0, limit: int = 2000) -> list[dict]:
    """Readings from the last `hours`, oldest first."""
    since = time.time() - hours * 3600
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM readings WHERE recorded_at >= ? ORDER BY recorded_at ASC LIMIT ?",
            (since, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def prune(db_path: str, retention_days: float) -> int:
    """Drop readings older than the retention window. Returns rows removed.

    At one reading every 30s this is ~2,900 rows a day, so the window is what
    stops an unattended NAS service growing without bound.
    """
    cutoff = time.time() - retention_days * 86400
    with _connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM readings WHERE recorded_at < ?", (cutoff,))
        removed = cursor.rowcount
    if removed:
        logger.info("Pruned %d readings older than %.1f days", removed, retention_days)
    return removed

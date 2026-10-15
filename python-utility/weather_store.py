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

# Not a measurement: the station's own report on whether its PMS reset line
# held the module off through the last sleep. Stored with the reading because
# that is the only channel the station has — it is mounted outside with a power
# lead and nothing reads its serial console.
_FLAGS = ["pms_hold_ok"]

_COLUMNS = list(FIELDS) + ["aqi"] + _FLAGS

# The furthest back a backfilled reading may be filed. The station holds unsent
# readings in RTC memory through a hub outage and posts them with an `age_s`
# saying how old each one is; this bounds what a wrong or rolled-over counter
# can do to the history.
MAX_BACKFILL_AGE = 7 * 86400


class ValidationError(ValueError):
    """The posted reading was not usable."""


def _connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# Every column the table should have, with its type. Used both to create the
# table and to bring an older one up to date.
_SCHEMA: dict[str, str] = (
    {"recorded_at": "REAL NOT NULL"}
    | {name: "REAL" for name in FIELDS}
    | {"aqi": "INTEGER"}
    | {name: "INTEGER" for name in _FLAGS}
)


def init(db_path: str) -> None:
    with _connect(db_path) as conn:
        columns = ", ".join(f"{name} {decl}" for name, decl in _SCHEMA.items())
        conn.execute(f"CREATE TABLE IF NOT EXISTS readings ({columns})")

        # CREATE TABLE IF NOT EXISTS does nothing to a table that already
        # exists, so a new column has to be added explicitly or every insert
        # naming it fails. There is a live database with weeks of readings in
        # it; migrating in place is the only option that keeps them.
        have = {row["name"] for row in conn.execute("PRAGMA table_info(readings)")}
        for name, decl in _SCHEMA.items():
            if name in have:
                continue
            # NOT NULL cannot be added to a populated table without a default,
            # and recorded_at is in the original schema anyway.
            conn.execute(f"ALTER TABLE readings ADD COLUMN {name} {decl.replace(' NOT NULL', '')}")
            logger.info("Added column %s to readings", name)

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

    # A tri-state on the wire: absent means the station has not checked yet
    # (its first wake after a power cut), so there is nothing to record.
    if "pms_hold_ok" in payload and payload["pms_hold_ok"] is not None:
        flag = payload["pms_hold_ok"]
        if isinstance(flag, bool):
            reading["pms_hold_ok"] = int(flag)
        elif isinstance(flag, int) and flag in (0, 1):
            reading["pms_hold_ok"] = flag
        else:
            raise ValidationError("pms_hold_ok must be true, false, 0 or 1")

    # A payload carrying only a flag is not a reading. Storing it would push a
    # real reading out of 'latest' and show the displays a row with no numbers.
    if not any(name in reading for name in list(FIELDS) + ["aqi"]):
        raise ValidationError("no usable fields in reading")

    return reading


def backfill_age(payload: Any) -> float:
    """Seconds between a reading being taken and it being posted.

    The station cannot stamp a reading with a wall-clock time — it never asks
    an NTP server — so when it drains readings held through a hub outage it
    says how old each one is and leaves the arithmetic here. Zero, which is
    also what an absent field means, is 'now'.
    """
    if not isinstance(payload, dict) or payload.get("age_s") is None:
        return 0.0
    age = payload["age_s"]
    if isinstance(age, bool) or not isinstance(age, (int, float)):
        raise ValidationError(f"age_s must be a number, got {type(age).__name__}")
    age = float(age)
    if age != age:  # NaN
        raise ValidationError("age_s is not a number")
    if not 0.0 <= age <= MAX_BACKFILL_AGE:
        raise ValidationError(f"age_s={age} is outside 0..{MAX_BACKFILL_AGE}")
    return age


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

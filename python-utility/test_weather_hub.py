"""Tests for the weather data hub — storage, validation, endpoints and auth.

    python test_weather_hub.py

Uses a temporary database; touches no real hardware. Exits non-zero on failure.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import weather_store  # noqa: E402

failures: list[str] = []


def check(label, condition, detail=""):
    print(f"  {'ok ' if condition else 'BAD'} {label}{(' — ' + str(detail)) if detail else ''}")
    if not condition:
        failures.append(label)


def section(name):
    print(f"\n{name}")


GOOD = {
    "temperature_c": 21.4,
    "humidity_pct": 48.2,
    "pressure_hpa": 1013.2,
    "pm1": 3.1,
    "pm25": 7.4,
    "pm10": 9.0,
    "aqi": 1,
}

db = str(Path(tempfile.mkdtemp()) / "weather.db")
weather_store.init(db)

# --------------------------------------------------------------------------
section("validation accepts a full reading")
r = weather_store.validate(dict(GOOD))
check("all seven fields kept", sorted(r) == sorted(GOOD), sorted(r))
check("aqi stays an int", isinstance(r["aqi"], int))

section("validation tolerates absent optional sensors")
partial = weather_store.validate({"temperature_c": 5.0, "humidity_pct": 60.0})
check("missing pressure and PM are fine", sorted(partial) == ["humidity_pct", "temperature_c"], sorted(partial))
none_ok = weather_store.validate({"temperature_c": 5.0, "pressure_hpa": None})
check("explicit null is skipped, not stored", "pressure_hpa" not in none_ok, none_ok)

section("validation rejects what would corrupt the display")
for label, payload in [
    ("temperature far out of range", {"temperature_c": -400}),
    ("humidity above 100", {"humidity_pct": 150}),
    ("aqi outside the Matter enum", {"aqi": 9}),
    ("aqi as a float", {"aqi": 1.5}),
    ("a string where a number belongs", {"temperature_c": "warm"}),
    ("a bool where a number belongs", {"temperature_c": True}),
    ("nothing usable at all", {}),
    ("not an object", [1, 2, 3]),
]:
    try:
        weather_store.validate(payload)
        check(label, False, "was accepted")
    except weather_store.ValidationError as err:
        check(label, True, str(err))

section("NaN is rejected")
try:
    weather_store.validate({"temperature_c": float("nan")})
    check("NaN rejected", False, "was accepted")
except weather_store.ValidationError:
    check("NaN rejected", True)

# --------------------------------------------------------------------------
section("storage")
check("empty store has no latest", weather_store.latest(db) is None)
weather_store.record(db, weather_store.validate(dict(GOOD)), recorded_at=time.time() - 60)
weather_store.record(db, weather_store.validate({"temperature_c": 22.5}))
row = weather_store.latest(db)
check("latest is the newest row", row["temperature_c"] == 22.5, row["temperature_c"])
check("absent fields come back NULL", row["humidity_pct"] is None)

section("history and retention")
weather_store.record(db, weather_store.validate({"temperature_c": 1.0}), recorded_at=time.time() - 40 * 86400)
check("old row is outside a 24h window", len(weather_store.history(db, hours=24)) == 2, len(weather_store.history(db, hours=24)))
check("but inside a wide one", len(weather_store.history(db, hours=24 * 60)) == 3)
removed = weather_store.prune(db, retention_days=30)
check("prune removes only what is past retention", removed == 1, removed)
check("recent rows survive", len(weather_store.history(db, hours=24 * 60)) == 2)

# --------------------------------------------------------------------------
section("endpoints")
import app as flaskapp  # noqa: E402

flaskapp.config.WEATHER_DB_PATH = db
flaskapp.config.INGEST_TOKEN = "ingest-secret"
flaskapp.config.READ_TOKEN = "read-secret"
flaskapp.config.ACTION_TOKEN = "action-secret"
flaskapp.config.WEATHER_STALE_AFTER = 120

c = flaskapp.app.test_client()
ING = {"Authorization": "Bearer ingest-secret"}
RD = {"Authorization": "Bearer read-secret"}

r = c.post("/ingest", json=GOOD, headers=ING)
check("ingest accepts a good reading", r.status_code == 200, r.get_json())

r = c.post("/ingest", json={"temperature_c": -400}, headers=ING)
check("ingest rejects a bad reading with 400", r.status_code == 400, r.get_json())
check("and says what was wrong", "range" in str(r.get_json().get("error")), r.get_json().get("error"))

r = c.get("/api/weather", headers=RD)
body = r.get_json()
check("weather serves the latest reading", r.status_code == 200 and body["temperature_c"] == 21.4, body)
check("carries a freshness age", body["age_seconds"] < 5, body.get("age_seconds"))
check("and is not marked stale", body["stale"] is False)

section("staleness is reported honestly")
stale_db = str(Path(tempfile.mkdtemp()) / "stale.db")
weather_store.init(stale_db)
weather_store.record(stale_db, weather_store.validate(dict(GOOD)), recorded_at=time.time() - 3600)
flaskapp.config.WEATHER_DB_PATH = stale_db
body = c.get("/api/weather", headers=RD).get_json()
check("an hour-old reading is flagged stale", body["stale"] is True, body["age_seconds"])
flaskapp.config.WEATHER_DB_PATH = db

section("no readings yet is a 404, not a crash")
empty_db = str(Path(tempfile.mkdtemp()) / "empty.db")
weather_store.init(empty_db)
flaskapp.config.WEATHER_DB_PATH = empty_db
r = c.get("/api/weather", headers=RD)
check("404 with a usable hint", r.status_code == 404 and "ingest" in str(r.get_json()), r.get_json())
flaskapp.config.WEATHER_DB_PATH = db

section("history endpoint")
body = c.get("/api/weather/history?hours=24", headers=RD).get_json()
check("returns readings", body["count"] >= 1, body["count"])
check("rejects a nonsense hours value", c.get("/api/weather/history?hours=abc", headers=RD).status_code == 400)

# --------------------------------------------------------------------------
section("the three tokens are genuinely separate")
check("ingest rejects no token", c.post("/ingest", json=GOOD).status_code == 401)
check("ingest rejects the READ token", c.post("/ingest", json=GOOD, headers=RD).status_code == 401)
check("weather rejects the INGEST token", c.get("/api/weather", headers=ING).status_code == 401)
check("history rejects the INGEST token", c.get("/api/weather/history", headers=ING).status_code == 401)
check("launch rejects the READ token", c.post("/launch-tv-app", json={}, headers=RD).status_code == 401)
check("X-Auth-Token header also works", c.get("/api/weather", headers={"X-Auth-Token": "read-secret"}).status_code == 200)

section("an unset token leaves that endpoint open (the Edge driver case)")
flaskapp.config.ACTION_TOKEN = ""
r = c.post("/launch-tv-app", json={"target_device": "nonsense"})
check("launch reachable with no credentials", r.status_code == 400, r.status_code)
flaskapp.config.ACTION_TOKEN = "action-secret"

section("diagnostics report the auth posture")
body = c.get("/config").get_json()
check("config flags open endpoints", body["auth"]["ingest"] == "token required", body["auth"])
flaskapp.config.INGEST_TOKEN = ""
check("and warns when ingest is open", "OPEN" in c.get("/config").get_json()["auth"]["ingest"])
flaskapp.config.INGEST_TOKEN = "ingest-secret"
body = c.get("/health").get_json()
check("health reports data is flowing", body["weather"]["has_readings"] is True, body["weather"])

print("\n" + ("FAILURES: " + ", ".join(failures) if failures else "all checks passed"))
sys.exit(1 if failures else 0)

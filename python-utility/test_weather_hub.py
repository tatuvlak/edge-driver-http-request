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

# --------------------------------------------------------------------------
section("the PMS hold flag")
# Not a measurement: the station's report on whether its reset line actually
# held the sensor off through the last sleep. It has no other way to tell us —
# it is mounted outside with a power lead and nothing reads its serial console.
for label, value, want in [
    ("true becomes 1", True, 1),
    ("false becomes 0", False, 0),
    ("1 is accepted", 1, 1),
    ("0 is accepted", 0, 0),
]:
    got = weather_store.validate({"temperature_c": 5.0, "pms_hold_ok": value})
    check(label, got.get("pms_hold_ok") == want, got)

check("absent means not checked, so nothing is stored",
      "pms_hold_ok" not in weather_store.validate({"temperature_c": 5.0}))
check("null means not checked either",
      "pms_hold_ok" not in weather_store.validate({"temperature_c": 5.0, "pms_hold_ok": None}))
for bad in ("yes", 2, -1, 0.5):
    try:
        weather_store.validate({"temperature_c": 5.0, "pms_hold_ok": bad})
        check(f"rejects pms_hold_ok={bad!r}", False)
    except weather_store.ValidationError:
        check(f"rejects pms_hold_ok={bad!r}", True)

# A flag on its own is not a reading. Storing it would push a real reading out
# of 'latest' and show the displays a row with no numbers in it.
try:
    weather_store.validate({"pms_hold_ok": False})
    check("a flag with no reading is rejected", False)
except weather_store.ValidationError as err:
    check("a flag with no reading is rejected", True, err)

# --------------------------------------------------------------------------
section("backfilled readings")
check("no age_s means now", weather_store.backfill_age({"temperature_c": 1.0}) == 0.0)
check("null age_s means now", weather_store.backfill_age({"age_s": None}) == 0.0)
check("an age comes back as seconds", weather_store.backfill_age({"age_s": 900}) == 900.0)
for bad in ("soon", -1, weather_store.MAX_BACKFILL_AGE + 1, float("nan"), True):
    try:
        weather_store.backfill_age({"age_s": bad})
        check(f"rejects age_s={bad!r}", False)
    except weather_store.ValidationError:
        check(f"rejects age_s={bad!r}", True)

# The point of all this: a reading held through an outage must land in the
# history at the time it was MEASURED, not the time the NAS came back.
backfill_db = str(Path(tempfile.mkdtemp()) / "backfill.db")
weather_store.init(backfill_db)
r = c.post("/ingest", json={**GOOD, "temperature_c": 11.0}, headers=ING)
flaskapp.config.WEATHER_DB_PATH = backfill_db
now = time.time()
c.post("/ingest", json={**GOOD, "temperature_c": 1.0}, headers=ING)
r = c.post("/ingest", json={**GOOD, "temperature_c": 2.0, "age_s": 1800}, headers=ING)
check("a backfilled push is accepted", r.status_code == 200, r.get_json())
check("and says so", r.get_json().get("backfilled") is True, r.get_json())

rows = weather_store.history(backfill_db, hours=24)
by_temp = {row["temperature_c"]: row["recorded_at"] for row in rows}
check("both rows stored", sorted(by_temp) == [1.0, 2.0], sorted(by_temp))
check("the backfilled row is filed half an hour back",
      1750 < now - by_temp[2.0] < 1850, round(now - by_temp[2.0]))
check("the fresh row is filed now", abs(now - by_temp[1.0]) < 10, round(now - by_temp[1.0]))
# Backfill must never displace the newest reading on the displays.
check("latest is still the fresh one",
      weather_store.latest(backfill_db)["temperature_c"] == 1.0,
      weather_store.latest(backfill_db)["temperature_c"])

# --------------------------------------------------------------------------
section("migrating a database that predates these columns")
# There is a live database with weeks of readings in it. CREATE TABLE IF NOT
# EXISTS does nothing to a table that already exists, so without a migration
# every insert naming a new column would fail and the sensor would go quiet.
import sqlite3  # noqa: E402

legacy = str(Path(tempfile.mkdtemp()) / "legacy.db")
with sqlite3.connect(legacy) as conn:
    conn.execute(
        """CREATE TABLE readings (recorded_at REAL NOT NULL, temperature_c REAL,
           humidity_pct REAL, pressure_hpa REAL, pm1 REAL, pm25 REAL, pm10 REAL,
           aqi INTEGER)"""
    )
    conn.execute("INSERT INTO readings (recorded_at, temperature_c) VALUES (?, ?)",
                 (time.time() - 60, 19.5))

weather_store.init(legacy)
cols = {row[1] for row in sqlite3.connect(legacy).execute("PRAGMA table_info(readings)")}
check("the new column was added", "pms_hold_ok" in cols, sorted(cols))
check("the existing reading survived",
      weather_store.latest(legacy)["temperature_c"] == 19.5)
weather_store.record(legacy, weather_store.validate({"temperature_c": 20.5, "pms_hold_ok": False}))
check("and a reading using the new column stores",
      weather_store.latest(legacy)["pms_hold_ok"] == 0,
      weather_store.latest(legacy)["pms_hold_ok"])
weather_store.init(legacy)   # must be idempotent
check("init is idempotent", weather_store.latest(legacy)["temperature_c"] == 20.5)

# gunicorn runs the service with several workers and every one of them imports
# app.py, which calls init(). They can therefore read the same PRAGMA, all
# conclude a column is missing, and all try to add it - and all but one get
# "duplicate column name". The first version of this migration did exactly
# that in production: the column was added, a second worker raised, and the
# traceback was swallowed by app.py's try/except, so the service came up
# looking healthy with one worker having skipped the index creation below.
import threading  # noqa: E402

racy = str(Path(tempfile.mkdtemp()) / "racy.db")
with sqlite3.connect(racy) as conn:
    conn.execute("CREATE TABLE readings (recorded_at REAL NOT NULL, temperature_c REAL)")
    conn.execute("INSERT INTO readings (recorded_at, temperature_c) VALUES (?, ?)",
                 (time.time(), 18.0))

WORKERS = 4
ready = threading.Barrier(WORKERS)
errors: list[BaseException] = []


def migrate():
    ready.wait()          # start them together, to make the race likely
    try:
        weather_store.init(racy)
    except BaseException as exc:       # noqa: BLE001 - the point is to catch any
        errors.append(exc)


threads = [threading.Thread(target=migrate) for _ in range(WORKERS)]
for t in threads:
    t.start()
for t in threads:
    t.join()

check(f"{WORKERS} workers migrating at once, none raised", not errors,
      "; ".join(f"{type(e).__name__}: {e}" for e in errors))

with sqlite3.connect(racy) as conn:
    cols = [row[1] for row in conn.execute("PRAGMA table_info(readings)")]
    idx = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='readings'")]
check("every column present exactly once", len(cols) == len(set(cols)) == len(weather_store._SCHEMA),
      cols)
# The loser of the race must still reach the index, which is what the
# per-column catch is for.
check("the index was created", "idx_recorded_at" in idx, idx)
check("the existing reading survived the scramble",
      weather_store.latest(racy)["temperature_c"] == 18.0)

# --------------------------------------------------------------------------
section("timestamps carry their offset")
# A naive ISO string - no offset, no Z - is rendered in whatever zone the
# container happens to be set to, and this one runs in UTC. The TV app's
# new Date() then reads it as LOCAL time, so the dashboard clock was wrong by
# exactly the viewer's UTC offset. age_seconds is epoch arithmetic and was
# always right, which is why the staleness logic looked perfect while the
# displayed time was two hours out.
from datetime import datetime, timezone  # noqa: E402

flaskapp.config.WEATHER_DB_PATH = db
body = c.get("/api/weather", headers=RD).get_json()
stamp = body["recorded_at"]
parsed = datetime.fromisoformat(stamp)
check("the reading's timestamp is timezone-aware", parsed.tzinfo is not None, stamp)
# The real test: parsed back, it must point at the same instant the age says.
drift = abs((datetime.now(timezone.utc) - parsed).total_seconds() - body["age_seconds"])
check("and agrees with age_seconds to the second", drift < 2, round(drift, 2))

hist = c.get("/api/weather/history?hours=24", headers=RD).get_json()
check("history timestamps too",
      all(datetime.fromisoformat(r["recorded_at"]).tzinfo is not None
          for r in hist["readings"]),
      hist["readings"][0]["recorded_at"] if hist["readings"] else "none")

ing = c.post("/ingest", json=GOOD, headers=ING).get_json()
check("and the ingest receipt",
      datetime.fromisoformat(ing["recorded_at"]).tzinfo is not None, ing["recorded_at"])
check("as does /health",
      datetime.fromisoformat(c.get("/health").get_json()["timestamp"]).tzinfo is not None)

print("\n" + ("FAILURES: " + ", ".join(failures) if failures else "all checks passed"))
sys.exit(1 if failures else 0)

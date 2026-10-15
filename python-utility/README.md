# Weather hub and TV launcher

A small Flask service on the QNAP. It does two jobs:

1. Launches the Tizen weather app on a display, over the LAN, when the Edge
   driver asks it to.
2. Stores the weather station's readings and serves them to the TV and phone
   apps.

Neither job calls the SmartThings API.

## Endpoints

| Method | Path | Guarded by | Purpose |
|---|---|---|---|
| POST | `/launch-tv-app` | `ACTION_TOKEN` | Open the app on a display. Called by the Edge driver. |
| POST | `/ingest` | `INGEST_TOKEN` | Record a reading. Called by the ESP32. |
| GET | `/api/weather` | `READ_TOKEN` | The latest reading. |
| GET | `/api/weather/history` | `READ_TOKEN` | Readings over a window (`?hours=`). |
| GET | `/displays` | — | Which displays are reachable. `?rediscover=1` forces a MAC scan. |
| GET | `/health` | — | Liveness, version, and whether data is arriving. |
| GET | `/config` | — | Effective settings, for debugging. Reports no secrets. |
| GET | `/device-status` | — | **Legacy.** Left from the SmartThings-API version; to be removed. |

`/oauth/*` routes also survive from the old external-callback design and are
not part of the current flow.

### What `/ingest` accepts

Every measurement is optional — the pressure sensor may be absent and a PMS
read can fail on any cycle — but anything present must be a number in a
plausible range, and a body with no measurement at all is rejected.

| Field | Meaning |
|---|---|
| `temperature_c`, `humidity_pct`, `pressure_hpa` | BME280 |
| `pm1`, `pm25`, `pm10` | PMS5003 |
| `aqi` | Matter's AirQualityEnum, 0-6 |
| `age_s` | How long ago this reading was **taken**, in seconds. Absent or 0 means now. |
| `pms_hold_ok` | Whether the station's PMS reset line held the module off through the last sleep. Absent means it has not checked yet. |

`age_s` exists because the station holds readings it could not send while this
service was down — it keeps an hour of them in RTC memory — and drains them
once this answers again. It has no clock of its own (it never asks an NTP
server), so it reports each reading's age and the hub does the subtraction.
A backfilled reading is filed under the time it was measured, so it lands in
the history where it belongs rather than bunched up at the moment the NAS came
back. It also cannot displace the newest reading on the displays, since
`/api/weather` orders by recorded time.

`pms_hold_ok` is not a measurement. The station is mounted outside with only a
power lead, and nothing reads its serial console, so this is the only channel
it has for reporting a fault that the readings themselves cannot show. A loose
reset wire leaves the sensor's fan running continuously — about 100mA and the
fan's rated life, spent for nothing — and is otherwise audible only to someone
standing next to it. `false` surfaces as a notice on the TV dashboard.

Send a token as `Authorization: Bearer <token>` or `X-Auth-Token: <token>`.
**An unset token leaves that endpoint open** — deliberate, so the Edge driver
keeps working while `ACTION_TOKEN` is empty, but it means an empty
`INGEST_TOKEN` or `READ_TOKEN` is a hole rather than a default.

## The three tokens

They are separate because the blast radii are completely different:

| Token | Held by | If it leaked |
|---|---|---|
| `INGEST_TOKEN` | the ESP32 | someone could forge sensor readings |
| `READ_TOKEN` | **inside the .wgt on the TV** and the phone app | someone could read your weather |
| `ACTION_TOKEN` | the Edge driver | someone could open an app on your TV |

The read token ships inside a package on a television, so it must never be the
one that can write. Generate each separately:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Configuration

Copy `.env.no-api.example` to `.env` and fill it in. Every setting is
documented in that file; the ones that bite:

- **`TV_MAC_*` matters more than `TV_HOST_*`.** The address is a hint. The MAC
  is the identity, and it is what lets a display be found again after DHCP
  moves it. Without it, a moved display means editing `.env`.
- **`WEATHER_STALE_AFTER` must exceed the sensor's cycle.** The station sleeps
  `SENSOR_SLEEP_SECONDS` (300 by default) and is awake about 70s, so a reading
  lands roughly every 370s. Set it below that and every reading — including
  good ones — is served with `stale: true`, which makes the flag useless.

## Running it

Deployment is in
[`../DEPLOYMENT_QNAP_CONTAINER_STATION.md`](../DEPLOYMENT_QNAP_CONTAINER_STATION.md);
`docker-compose.no-api.yml` is the current compose file, and
`/share/Container/tv-app-launcher-no-api` is the live folder on the NAS.
`docker-compose.yml` and `/share/Container/tv-app-launcher` are the stopped
SmartThings-API deployment, kept as a rollback - updating that one by mistake
leaves the live service running old code with nothing to show for it. See
`../DEPLOYMENT_QNAP_CONTAINER_STATION.md`.

Note that it has **no `environment:` block**, on purpose. Container Station
resolves an application's compose file in a temporary directory where the
variables do not exist, so those entries would come out empty — and
`environment:` overrides `env_file:`, so it would silently blank the very
settings it appeared to set.

Locally:

```bash
pip install -r requirements.txt
cp .env.no-api.example .env   # then edit it
python app.py
```

## Tests

```bash
python test_weather_hub.py     # storage, validation, endpoints, the three tokens
python test_discovery.py       # a display is identified by MAC, not by whatever answered
python test_local_launch.py    # the launch path and its reporting
```

They use temporary databases and touch no hardware. Each exits non-zero on
failure.

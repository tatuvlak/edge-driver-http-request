# TV App Launcher — weather ecosystem, without the SmartThings API

Launches a Samsung Tizen weather app on a TV from a SmartThings routine, and
hosts the weather station's readings for that app to display — using no
SmartThings cloud API at all.

The SmartThings developer API becomes a paid subscription in October 2026.
Matter commissioning, hub-local Edge drivers and the SmartThings app itself are
product features and are unaffected; it is the `api.smartthings.com/v1` calls
that a hobby project has to design out. This repo is the part of that work that
runs on the hub and on the NAS.

## How a launch happens

```
SmartThings routine
  (turns the TV on, then flips a virtual switch)
        │
        ▼
Edge driver on the hub          ← a routine cannot make an HTTP call, only
  POST /launch-tv-app             operate a device, so the driver is a switch
        │                         whose "on" means "make this request"
        ▼
Python service on the QNAP
  POST https://<display>:8002/api/v2/applications/<app-id>
        │
        ▼
The TV opens the weather app
```

Nothing in that chain touches SmartThings' cloud. The display's own REST API is
unauthenticated on the LAN — verified from a machine that had never paired with
it — so the service holds no credentials for the TVs at all.

## How the data gets there

```
ESP32-C6 weather station
  ├── Matter over Wi-Fi ──────────►  SmartThings app (unchanged, still free)
  └── POST /ingest ──────────────►  this service ──► GET /api/weather
                                                       │
                                            the TV app and the phone app
```

The station keeps its Matter endpoint, so its tile in the SmartThings app works
exactly as before. The second output is what replaces reading the sensor back
out of the cloud.

## Repository layout

| Path | What it is |
|---|---|
| `edge-driver/` | The Edge driver (Lua). Runs on the hub. |
| `python-utility/` | The Flask service. Runs on the QNAP in Container Station. |
| `phase0/` | The probe that established local TV control works, and its results. |
| `scripts/` | Small manual test helpers. |

## Documentation

| Document | For |
|---|---|
| [`DEPLOYMENT_QNAP_CONTAINER_STATION.md`](DEPLOYMENT_QNAP_CONTAINER_STATION.md) | Deploying the service. This is the path that has actually been followed successfully. |
| [`DEPLOYMENT_EDGE_DRIVER.md`](DEPLOYMENT_EDGE_DRIVER.md) | Packaging, publishing and installing the driver. |
| [`python-utility/README.md`](python-utility/README.md) | The service: endpoints, tokens, configuration. |
| [`phase0/RESULTS.md`](phase0/RESULTS.md) | What was measured on the real hardware, and what is still assumed. |

## Two things worth knowing before you change anything

**Publishing the Edge driver uses the developer API.** The driver runs on the
hub and keeps working regardless — it is the ability to *change* it that may
stop being free. Anything it might ever need should go in before October 2026,
which is why it already carries an optional bearer-token preference it does not
currently use.

**There are no DHCP reservations on this network.** Displays are identified by
MAC, not by address: the configured address is a hint, and when it stops
answering the service scans the subnet and caches where the display actually is.
This is not belt-and-braces — the M7 had already moved before the first
deployment finished.

## State

The TV launch no longer uses the SmartThings API, and the service hosts the
sensor's readings. Remaining work lives in the other repositories: the Tizen app
and the Android app reading from this service instead of the cloud, and retiring
the OAuth service that existed only to reach it.

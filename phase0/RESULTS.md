# Phase 0 results

Findings that Phase 2 depends on. Update this file as the remaining checks land.

## 1. Local TV control

### M7 — 32" Smart Monitor (LS32BM700UPXEN, `22_NIKEL_SMT`) — **PASS**

Tested 2026-09. Local app launch works, but **only via REST**.

| Mechanism | Result |
|-----------|--------|
| WebSocket `run_app` `DEEP_LINK` (`ed.apps.launch`) | accepted, ignored |
| WebSocket `run_app` `NATIVE_LAUNCH` | accepted, ignored |
| **REST `POST /api/v2/applications/{app_id}`** (`rest_app_run`) | **works** |

Also established:

- Pairing on port 8002 succeeds; token persisted and reusable.
- Key input works — `KEY_HOME` visibly moves the UI.
- `rest_app_status('tvweather1.tvweather')` returns a real payload, so the app
  id is correct as packaged and the REST app endpoints are live.
- `app_list()` (`ed.installedApp.get`) never answers on this firmware. Expected;
  do not depend on it anywhere.

**Implication for Phase 2:** use `rest_app_run()` as the primary launch call, not
`run_app()`. The WebSocket launch verb is dead on 2022+ firmware and fails
*silently* — it returns cleanly having done nothing, so it cannot be used as a
fallback that detects its own failure. If a WebSocket fallback is kept for older
sets, it must be tried only after REST fails, never before.

| Value | Setting |
|-------|---------|
| IP | 192.168.18.186 |
| MAC | 54:44:A3:5C:4B:16 |
| App id | `tvweather1.tvweather` |
| Client name | `WeatherHub` (token is bound to it — reuse verbatim) |
| Port | 8002 |

### S95 TV — Samsung S95BA 65 (QE65S95BATXXH, `22_PONTUSM_QD`) — **PASS**

Confirmed: local app launch works, same as the M7. Both displays behave
identically, which is unsurprising given both are 2022 sets.

| Value | Setting |
|-------|---------|
| IP | 192.168.18.187 |
| MAC | F0:70:4F:32:BF:DA |
| App id | `tvweather1.tvweather` |
| Port | 8002 |

This was the default `target_device`, so **check 1 is now fully closed** — both
displays verified, no assumptions left in the launch path.

### RESOLVED — the REST launch needs no pairing

Verified from a second Windows laptop that had never paired with the M7, with no
WebSocket session open: `GET` returned an app-status payload and `POST` opened
the weather app.

So `POST https://<display>:8002/api/v2/applications/<app-id>` is genuinely
unauthenticated on the local network. The earlier M7 result could not show this
on its own, because the probe held an authorized WebSocket session at the time —
leaving open the possibility that the TV granted REST access by source IP.
It does not.

**Consequence:** the QNAP service needs no pairing, no token file, no client
name, and no WebSocket handshake — which is how `tv_local.py` is written. It
also means the service carries no credentials of any kind for the displays.

### Library caveat — carry this into Phase 2

`samsungtvws` tolerates a **fixed** list of events while opening a connection
(`IGNORE_EVENTS_AT_STARTUP = ('ed.edenTV.update', 'ms.voiceApp.hide')`) and
raises `ConnectionFailure` on anything else. Models announce different things
first: the S95 sends `ms.remote.touchDisable`, which is not on that list, so the
connection is abandoned before pairing can even be offered.

Only `ms.channel.connect` and `ms.channel.unauthorized` are actually verdicts;
everything else during startup is chatter to read past. The probe patches
`samsungtvws.connection.IGNORE_EVENTS_AT_STARTUP` to that rule, which is bounded
by the socket timeout so an unresponsive TV still errors out.

This affects **the probe only**. The QNAP service never opens a WebSocket — it
launches over plain REST — so it neither needs this patch nor depends on
`samsungtvws` at all. Should a future display ever require the WebSocket path,
this caveat comes back with it, and the library version would need pinning.

### Wake-on-LAN — does not power the set on

Re-tested 2026-09-25 on the S95 with a corrected probe. The magic packet does
not turn the television on.

**The earlier "does not wake" result was right; the probe that produced it was
not.** Step 6 checked only whether TCP 8001 or 8002 answered — and a Samsung
set with network standby enabled keeps those ports open while the screen is
off. That is the same reason `curl` to port 8001 works at all. So the check
passed whether or not the packet did anything, with no control: it would have
passed without sending a packet. On the S95 run it reported PASS while the
screen stayed dark, and only the operator watching the television caught it.

The probe now reads `device.PowerState` from `/api/v2/` before and after the
packet, and requires a standby -> on transition. It refuses to run at all if
the set still reports `on`, rather than measuring nothing.

Powering on from the SmartThings app does work. That goes over the set's
persistent connection to Samsung's cloud, which a local magic packet cannot
imitate, so it is not evidence that WoL should work.

**Consequence for Phase 2:** drop Wake-on-LAN from the design, but add a
readiness wait. The TV's network stack is not up the instant the routine powers
it on, so the launch must poll port 8002 until it answers (with a timeout) and
retry the launch a few times rather than firing once and failing. This replaces
WoL as the thing that makes the trigger reliable.

If the assumption "the TV is always already on" ever stops holding, revisit —
`--wol` is still in the probe.

## 2. ESP32 flash / RAM baseline — **recorded**

Arduino IDE, ESP32 core 3.3.12, with the hub push included:

```
Sketch uses 2768838 bytes (88%) of program storage space. Maximum is 3145728 bytes.
Global variables use 140416 bytes (42%) of dynamic memory, leaving 187264 bytes
for local variables. Maximum is 327680 bytes.
```

RAM is comfortable. **Flash is not: 88% of the default partition leaves about
377 KB.** Matter plus WiFi plus HTTPClient is most of that, and the hub push
added little, but anything substantial from here — OTA, TLS to the hub, a
second radio stack — will not fit without changing the partition scheme. Check
this number after any dependency change.

The core upgrade from 3.3.5 to 3.3.12 broke the build: `pressure_measurement`
config fields dropped their `pressure_` prefix. Fixed in weather-station#3.
A core upgrade also wipes `libraries/Matter/src/MatterEndpoints/`, so the two
`MatterWeatherStation` files have to be copied in again every time.

## 4. SSDP discovery from the LAN — **works, both sets**

Tested 2026-09-25 with `phase0/ssdp_probe.py`. Both televisions answer and
carry enough to identify them:

```
192.168.18.219   F0:70:4F:32:BF:DA    Samsung S95BA 65 TV
192.168.18.221   54:44:A3:5C:4B:16    32" Smart Monitor M7
```

Three things this established:

- **`ssdp:all` is the only question that works.** Asking for
  `urn:samsung.com:device:RemoteControlReceiver:1` returned zero responders
  from either set. So a client has to ask broadly and filter by MAC.
- **Identification by MAC works** — `/api/v2/` on port 8001 reports `wifiMac`,
  the same value the utility matches on.
- **A set in standby does not answer.** The S95 was invisible until it was
  turned on. That is survivable, because a launch always follows the routine
  powering the display on, but a client should retry rather than asking once:
  a set that has just woken may take a moment to start advertising.

**Not established:** whether the SmartThings hub's Lua sandbox can send
multicast. Only a driver on a hub can show that, which is why the driver keeps
the utility as a fallback.

## 5. App launch over plain HTTP — **works, both sets**

`POST http://<display>:8001/api/v2/applications/<app-id>` returns `true` on
both televisions. Port 8002 is the same API over TLS with a self-signed
certificate; 8001 needs neither luasec nor disabled verification, which is
what makes a launch from the Edge sandbox practical.

## 3. Edge driver published — **confirmed**

Published 2026-09-21 and verified end to end: routine -> driver -> service ->
the display's own REST API, with the app opening on the M7.

| Value | Setting |
|-------|---------|
| Driver ID | `5590edb7-2c7b-4f82-9b99-b9205e3fc0f8` |
| Package key | `tv-app-launcher-v2` |
| Version | `2026-09-21T16:48:17` |
| Channel | `19b4055e-b69d-4187-a5ed-0df3ad540885` |

From the hub's driver log:

```
Switch ON command received
Sending request to: http://192.168.18.250:5000/launch-tv-app
Target device: m7
```

**Two drivers shared the name `TV App Launcher`.** A package key change at some
point left an orphan, `188d0a1b-9e46-4880-9e60-0d3e1f69b3bf`, last built in
January, never installed on the hub, and indistinguishable from the real one in
every CLI menu. The only reliable way to tell them apart is the driver ID that
`edge:drivers:package` prints — the list is not enough to pick from. Deleted
after this was verified.

**Consequence for any future publish:** `edge:drivers:package` before assigning,
and use the ID it prints rather than choosing by name. And note that an existing
device keeps the preferences it already has: a changed default in the profile
only reaches devices added afterwards, so preferences have to be checked in the
app after every update.


---

## Deployment status — QNAP

Running as `tv-app-launcher-no-api` on `winston:5000`, deployed via Container
Station 3.x Applications from `docker-compose.no-api.yml`. The old
SmartThings-based container is stopped but kept as a rollback.

Verified 2026-09-05:

| Check | Result |
|-------|--------|
| Service healthy, v3.1.0, local launch method | pass |
| `.env` reached the container; ingest and read tokens enforced | pass |
| Container reaches the displays across the LAN | pass |
| Sensor ingest -> read round trip, all seven fields, not stale | pass |
| Read token rejected on `/ingest`, ingest token rejected on `/api/weather` | pass |
| Real routine launch | **pass** |

End to end, from the logs:

```
Launch requested on M7 Monitor (m7)
M7 Monitor: 'tvweather1.tvweather' confirmed running
```

Routine -> Edge driver -> NAS -> the display's own REST API, with no SmartThings
API call in the chain. The TV confirmed the app was actually running rather than
merely accepting the command. No rediscovery line, so the cached .193 answered
straight away — the fast path, about 3.5 seconds end to end.

**Paid call site 3 of 3 is eliminated.** The remaining two are the TV app and the
phone app reading the sensor, which the data hub now serves.

**Discovery proved itself on first contact.** The M7 had already moved from
192.168.18.186 to .193, so the configured address was stale before deployment
even finished. `/displays?rediscover=1` identified it by MAC and cached the new
address. Without that, the launch would have failed against a config that looked
entirely correct — which is what the lack of DHCP reservations would have cost.

Networking is therefore confirmed: Container Station's bridge network reaches
the LAN, and the NAS is on the same segment as the displays.

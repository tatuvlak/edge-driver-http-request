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

### S95 TV — Samsung S95BA 65 (QE65S95BATXXH, `22_PONTUSM_QD`) — **assumed, not verified**

Reachable on 8001/8002, reports `TokenAuthSupport`, MAC `F0:70:4F:32:BF:DA` at
192.168.18.187. Pairing failed on `ms.remote.touchDisable` (see the library
caveat below); fixed but **not yet re-run**.

We are proceeding on the assumption that it behaves like the M7 — REST launch
works, WebSocket launch is ignored — because both are 2022 sets. That is a
reasonable guess, not a result. The S95 is the default `target_device`, so if the
assumption is wrong it surfaces the first time the routine runs against it. Run
the probe when convenient:

```powershell
python tv_local_control_test.py --ip 192.168.18.187 --token-file s95-token.txt
```

```powershell
python tv_local_control_test.py --ip 192.168.18.187 --token-file s95-token.txt
```

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

**The QNAP service needs the same patch**, or it will fail to connect to the S95
in exactly the same way. Pin the `samsungtvws` version too — this behaviour could
change under either an upgrade or a TV firmware update.

### Wake-on-LAN — **out of scope**

Tested on the M7 (Wi-Fi connected): does not wake. Not expected to work on the
S95 either. This does not matter: the SmartThings routine turns the display on
*before* triggering the launch, so the service only ever has to start an app on a
set that is already awake — which is exactly what was tested and works.

Turning a TV on from a routine is ordinary SmartThings app behaviour, not a
developer-API call, so it stays free after October 2026.

**Consequence for Phase 2:** drop Wake-on-LAN from the design, but add a
readiness wait. The TV's network stack is not up the instant the routine powers
it on, so the launch must poll port 8002 until it answers (with a timeout) and
retry the launch a few times rather than firing once and failing. This replaces
WoL as the thing that makes the trigger reliable.

If the assumption "the TV is always already on" ever stops holding, revisit —
`--wol` is still in the probe.

## 2. ESP32 flash / RAM baseline — not yet recorded

```
Sketch uses ___ bytes (__%) of program storage space.
Global variables use ___ bytes (__%) of dynamic memory.
```

## 3. Edge driver published — not yet confirmed

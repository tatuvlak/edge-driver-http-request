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

### S95 TV — **not yet tested**

The default `target_device` in `app.py`, so this one has to pass before Phase 2
can be considered de-risked. Different model and firmware generation; the M7
result does not transfer.

```powershell
python tv_local_control_test.py --ip <S95_IP> --token-file s95-token.txt
```

### Wake-on-LAN — **not yet tested**

Needed on both devices: the routine has to wake the display, not just drive one
that is already on.

```powershell
python tv_local_control_test.py --ip <IP> --token-file <file> --wol
```

## 2. ESP32 flash / RAM baseline — not yet recorded

```
Sketch uses ___ bytes (__%) of program storage space.
Global variables use ___ bytes (__%) of dynamic memory.
```

## 3. Edge driver published — not yet confirmed

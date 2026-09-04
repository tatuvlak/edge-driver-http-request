# Phase 0 — de-risk before writing migration code

Three checks to run **before** any of the SmartThings-API migration work starts.
All three need your own hardware and network, so none of them can be done from a
build agent. Nothing here changes production behaviour: the current
SmartThings-based system keeps working untouched while you run these.

Context: [migration plan](https://claude.ai/code/artifact/a30b0117-337a-44b7-a06e-82d8e67d3be6).

| # | Check | Why it is first | Time |
|---|-------|-----------------|------|
| 1 | Local TV control works | The only item that could force a redesign | ~10 min |
| 2 | ESP32 flash/RAM headroom | Phase 1 adds an HTTP client to a tight build | ~5 min |
| 3 | Edge driver published | The CLI publish path may need paid API access later | ~10 min |

---

## 1. Local TV control — the decisive test

Phase 2 replaces `SmartThingsAPI.launch_app()` in `python-utility/app.py` with
local control of the TV. That works on most Samsung sets, but `run_app` over the
local WebSocket behaves differently across models and firmware years, and some
2022+ sets restrict it. **Find out now**, on your actual TV, rather than after
rewriting the service around the assumption.

### Run it

On any machine on the **same subnet** as the TV — Samsung sets refuse WebSocket
connections across subnets and VLANs, so a NAS on a separate segment will fail
here for reasons that have nothing to do with the API.

```bash
cd phase0
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-phase0.txt

python tv_local_control_test.py --ip <TV_IP>
```

Turn the TV on first. On the first run it will show an on-screen pairing prompt —
accept it with the remote within 30 seconds.

To also test waking the set from standby (you will be asked to turn the TV off):

```bash
python tv_local_control_test.py --ip <TV_IP> --wol
```

If your Tizen app is packaged under a different id than the default
`tvweather1.tvweather`, pass `--app-id`.

### What it does

1. Checks TCP 8001/8002 are answering.
2. Reads the unauthenticated `/api/v2/` device info — model, firmware, MAC,
   whether the set wants token auth.
3. Pairs over the WebSocket and persists the token to `tv-token.txt`.
4. Lists installed apps and looks for yours.
5. **Launches the app** — tries `run_app` with both `DEEP_LINK` and
   `NATIVE_LAUNCH`, falls back to the REST launch, then tries to confirm the app
   is actually running.
6. Optionally sends a Wake-on-LAN magic packet and waits for the TV to answer.

Exit codes: `0` launch worked · `1` tested and failed · `2` inconclusive.

### Reading the result

**Watch the TV screen during step 5.** Some sets acknowledge the launch command
and then quietly ignore it, so a `[PASS]` line is weaker evidence than your own
eyes. The script says as much when it gets there.

- **It launched.** Phase 2 proceeds as planned. Record `TV_IP`, the MAC, the app
  id *the TV reported* (it is sometimes not the one you packaged), and keep
  `tv-token.txt`.
- **It did not launch.** The migration still stands — the sensor data path is
  where the recurring cost is, and that path is unaffected. Only the launch
  trigger needs rethinking, and the script prints the fallbacks in order of
  preference.

> **Carry the client name over.** The pairing token the TV issues is bound to the
> client name, which is `WeatherHub` in `CLIENT_NAME`. Phase 2 must use the same
> string, or the TV treats the QNAP as a new client and prompts again — which
> nobody is there to accept.

`tv-token.txt` is gitignored. It is a credential for controlling your TV: it
grants nothing beyond your LAN, but do not commit it.

---

## 2. ESP32 flash and RAM headroom

Phase 1 adds `HTTPClient` and a small JSON builder to the sketch. That is modest,
but `MatterWeatherStation.cpp` already logs `"Limit Reached?"` warnings when
creating clusters, so the build is not roomy. Get a baseline you can compare
against rather than discovering the ceiling mid-phase.

In Arduino IDE, open `weather-station/AirQualitySensor.ino`, select your ESP32-C6
board, and **Sketch → Verify/Compile**. Record the two summary lines:

```
Sketch uses X bytes (NN%) of program storage space.
Global variables use Y bytes (NN%) of dynamic memory.
```

Write those numbers down. After Phase 1, recompile and compare. Rules of thumb:

- Program storage above ~90% — change the partition scheme (Tools → Partition
  Scheme) to one with a larger app partition before adding anything else.
- Dynamic memory above ~80% — the Matter stack needs headroom at runtime for TLS
  sessions; treat this as the tighter constraint of the two.

If either is already close before Phase 1, say so and the push payload can be
trimmed (fixed-size `snprintf` instead of a JSON library saves several KB).

---

## 3. Publish the Edge driver while API access is free

The Edge driver's **runtime** is hub-local Lua talking to your LAN and is not
affected by the API pricing change. But `smartthings edge:drivers:package` and
`:publish` authenticate against the developer API, so redeploying a driver after
October 2026 may require the paid plan.

Nothing about the driver changes in this migration — Phase 2 keeps its contract
(`POST /launch-tv-app` on the LAN) and only swaps the implementation behind it.
So the current driver is the one you want installed:

```bash
cd edge-driver
smartthings edge:drivers:package .
smartthings edge:drivers:publish --channel=<YOUR_CHANNEL_ID>
```

Then confirm it is installed on the hub:

```bash
smartthings edge:drivers:installed
```

If you ever do need to push a driver change later, one month of the personal
plan covers it — this is a convenience, not a trap.

---

## When all three are done

Report back with:

1. Whether the app launched, and what the TV reported as its app id.
2. The two ESP32 compile figures.
3. Confirmation the driver is installed on the hub.

That is everything Phase 1 needs to start.

#!/usr/bin/env python3
"""Phase 0 probe: can we drive the TV locally, without the SmartThings API?

This answers the one question that could force a redesign of the migration:
does the TV's own WebSocket API let us wake the set and launch the weather app,
so that `SmartThingsAPI.launch_app()` in python-utility/app.py can be replaced
with local control instead of a cloud call?

Run it on any machine on the SAME SUBNET as the TV (Samsung sets refuse
WebSocket connections across subnets and VLANs). Nothing here writes to the TV
beyond launching your own app, and no SmartThings credentials are involved.

    pip install -r requirements-phase0.txt
    python tv_local_control_test.py --ip 192.168.1.42

Add --wol to also test Wake-on-LAN (you will be asked to turn the TV off).
"""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

try:
    from samsungtvws import SamsungTVWS
    from samsungtvws.exceptions import ConnectionFailure, HttpApiError, UnauthorizedError
except ImportError:
    sys.exit("Missing dependency. Run:  pip install -r requirements-phase0.txt")

try:
    from wakeonlan import send_magic_packet
except ImportError:
    send_magic_packet = None

# Port 8002 uses the TV's self-signed certificate; that is expected and the
# library disables verification deliberately. Keep the warning out of the report.
try:
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass


DEFAULT_APP_ID = "tvweather1.tvweather"

# The pairing token the TV issues is bound to this client name. Whatever you use
# here must be reused verbatim by the QNAP service in Phase 2, or the TV will
# treat it as a new client and pop the "allow?" prompt again.
CLIENT_NAME = "WeatherHub"

PASS, FAIL, WARN, SKIP = "[PASS]", "[FAIL]", "[WARN]", "[SKIP]"

results: dict[str, tuple[str, str]] = {}


def record(step: str, status: str, detail: str = "") -> None:
    results[step] = (status, detail)
    line = f"  {status} {step}"
    if detail:
        line += f" — {detail}"
    print(line)


def header(text: str) -> None:
    print(f"\n{text}\n{'-' * len(text)}")


def call_with_timeout(fn: Callable[[], Any], seconds: float) -> tuple[str, Any]:
    """Run fn on a daemon thread and give up after `seconds`.

    samsungtvws makes blocking recv() calls that depend on a TV actually
    answering. Several models accept a request and then say nothing at all, so
    we cap the wait here rather than trusting the library's socket timeout.
    Returns ("ok", value) | ("error", exc) | ("timeout", None).
    """
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["value"] = fn()
        except Exception as err:  # noqa: BLE001 - reported to the caller
            box["error"] = err

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(seconds)

    if thread.is_alive():
        return "timeout", None
    if "error" in box:
        return "error", box["error"]
    return "ok", box.get("value")


# --------------------------------------------------------------------------
# 1. Reachability
# --------------------------------------------------------------------------

def probe_ports(ip: str) -> bool:
    header("1. Network reachability")
    open_ports = []
    for port in (8001, 8002):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        reachable = sock.connect_ex((ip, port)) == 0
        sock.close()
        if reachable:
            open_ports.append(port)
            record(f"TCP {port} open", PASS)
        else:
            record(f"TCP {port} open", FAIL, "no answer (TV off, or wrong subnet)")

    if not open_ports:
        print(
            "\n  The TV is not answering at all. Before reading anything else into\n"
            "  that: make sure the set is ON, and that this machine is on the same\n"
            "  subnet — not a guest SSID, not a separate VLAN."
        )
        return False
    return True


# --------------------------------------------------------------------------
# 2. Device info (unauthenticated — tells us what we are dealing with)
# --------------------------------------------------------------------------

def probe_device_info(ip: str) -> dict:
    header("2. Device identity")
    info: dict = {}
    for scheme, port in (("https", 8002), ("http", 8001)):
        url = f"{scheme}://{ip}:{port}/api/v2/"
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(url, timeout=5, context=ctx) as resp:
                info = json.loads(resp.read().decode())
            break
        except Exception:
            continue

    if not info:
        record("REST device info", FAIL, "could not read /api/v2/")
        return {}

    device = info.get("device", {})
    model = device.get("modelName") or "?"
    name = device.get("name") or "?"
    year = device.get("model") or "?"
    mac = device.get("wifiMac") or ""
    token_auth = str(device.get("TokenAuthSupport", "")).lower() == "true"
    power = device.get("PowerState", "unknown")

    record("REST device info", PASS, f"{name} / {model} (model code {year})")
    record("MAC address", PASS if mac else WARN, mac or "not reported — pass --mac for the WoL test")
    record("Power state", PASS, power)

    if token_auth:
        record("Token auth supported", PASS, "use port 8002 (encrypted + paired)")
    else:
        record("Token auth supported", WARN, "older set — port 8001, unpaired")

    return {"mac": mac, "token_auth": token_auth, "model": model}


# --------------------------------------------------------------------------
# 3. Pairing
# --------------------------------------------------------------------------

def probe_pairing(ip: str, token_file: Path, token_auth: bool) -> SamsungTVWS | None:
    header("3. Pairing / authorisation")
    port = 8002 if token_auth else 8001

    if not token_file.exists():
        print(
            f"  Connecting as \"{CLIENT_NAME}\". If this is the first run, the TV will\n"
            "  show an on-screen prompt — accept it with the remote within 30 seconds.\n"
        )

    tv = SamsungTVWS(
        host=ip,
        port=port,
        token_file=str(token_file),
        name=CLIENT_NAME,
        timeout=30,
    )

    try:
        tv.open()
    except UnauthorizedError:
        record("WebSocket pairing", FAIL, "TV refused authorisation (prompt declined or timed out)")
        print(
            "\n  Re-run and accept the prompt. If no prompt appeared at all, check\n"
            "  Settings > General > External Device Manager > Device Connect Manager\n"
            "  and clear any stale entry for this client name."
        )
        return None
    except (ConnectionFailure, OSError) as err:
        record("WebSocket pairing", FAIL, f"{type(err).__name__}: {err}")
        return None

    record("WebSocket pairing", PASS, f"connected on port {port}")
    if token_file.exists():
        record("Token persisted", PASS, str(token_file))
    else:
        record("Token persisted", WARN, "no token file written (unpaired mode)")
    return tv


# --------------------------------------------------------------------------
# 4. App list
# --------------------------------------------------------------------------

def probe_app_list(tv: SamsungTVWS, app_id: str) -> tuple[bool, bool]:
    """Returns (app_found, connection_stalled).

    This step is informational only — step 5 is what decides the migration — so
    nothing here is allowed to hold the run up.
    """
    header("4. Installed applications")
    print(
        "  Asking the TV what it has installed. This is optional and many 2022+\n"
        "  sets never answer, so it may pause for up to 15 seconds before moving on.\n"
    )

    outcome, apps = call_with_timeout(tv.app_list, 15)

    if outcome == "timeout":
        record("List installed apps", WARN, "no reply within 15s — firmware ignores this request")
        print("  Expected on newer firmware. Reconnecting, then on to the launch test.")
        return False, True

    if outcome == "error":
        record("List installed apps", WARN, f"{type(apps).__name__}: {apps}")
        print("  Not fatal — launching by id can still work. Continuing.")
        return False, True

    if not apps:
        record("List installed apps", WARN, "TV returned an empty list")
        print("  Not fatal — launching by id can still work. Continuing.")
        return False, False

    record("List installed apps", PASS, f"{len(apps)} apps reported")

    wanted = app_id.lower()
    match = None
    for app in apps:
        candidate = str(app.get("appId", ""))
        if candidate.lower() == wanted or wanted.split(".")[0] in candidate.lower():
            match = app
            break

    if match:
        record("Weather app visible", PASS, f"{match.get('name')} → appId={match.get('appId')}")
        if str(match.get("appId")) != app_id:
            print(
                f"\n  NOTE: the TV knows this app as '{match.get('appId')}', not '{app_id}'.\n"
                "  Use the TV's id in TV_APP_ID when you configure the QNAP service."
            )
    else:
        record("Weather app visible", WARN, f"'{app_id}' not in the list")
        print("  Sideloaded apps are often omitted from this list. The launch test below is what counts.")
    return match is not None, False


# --------------------------------------------------------------------------
# 5. Launch — the decisive test
# --------------------------------------------------------------------------

LAUNCH_METHODS = [
    ("WebSocket run_app DEEP_LINK", lambda tv, aid: tv.run_app(aid, app_type="DEEP_LINK")),
    ("WebSocket run_app NATIVE_LAUNCH", lambda tv, aid: tv.run_app(aid, app_type="NATIVE_LAUNCH")),
    ("REST POST /applications", lambda tv, aid: tv.rest_app_run(aid)),
]


def try_every_launch_method(tv: SamsungTVWS, app_id: str, interactive: bool) -> bool:
    """Attempt each launch mechanism, confirming with the operator after each.

    run_app sends over the websocket and never reports back, so an exception is
    not available as a failure signal — an unsupported request looks exactly
    like a successful one. The only way to know which method works is to try
    them all and look at the screen, so that is what this does.
    """
    for label, launch in LAUNCH_METHODS:
        try:
            launch(tv, app_id)
        except Exception as err:
            record(label, FAIL, f"{type(err).__name__}: {err}")
            continue

        time.sleep(4)

        if not interactive:
            record(label, WARN, "sent; cannot confirm without someone watching")
            continue

        if ask_yes_no(f"{label}: did it open?"):
            record(label, PASS, "confirmed on screen")
            return True
        record(label, FAIL, "accepted, nothing happened")

    return False


def probe_launch(tv: SamsungTVWS, app_id: str, interactive: bool) -> bool:
    header("5. Launching the app (the decisive test)")

    # Does the TV even recognise this id? A real payload here means the id is
    # right and REST app endpoints work, which is worth knowing before blaming
    # the app for a launch that never happens.
    try:
        status = tv.rest_app_status(app_id)
        record("App id recognised", PASS,
               f"REST knows '{app_id}' (visible={status.get('visible')} running={status.get('running')})")
    except Exception as err:
        record("App id recognised", WARN, f"no status for '{app_id}' ({type(err).__name__})")
        print("  The TV may not know this id. If the launches below all fail, that is")
        print("  the first thing to re-check.")

    print("\n  Trying each launch mechanism in turn. Watch the screen and answer")
    print("  after each one — the first that works is the one Phase 2 will use.\n")

    opened = try_every_launch_method(tv, app_id, interactive)

    if not interactive:
        print("\n  Non-interactive run: commands were sent but nothing was confirmed.")
        print("  Re-run interactively for a real answer.")
        return False

    record("App actually opened", PASS if opened else FAIL,
           "confirmed on screen" if opened else "no method worked")
    return opened


# --------------------------------------------------------------------------
# D. Diagnosis — only runs when the launch failed
# --------------------------------------------------------------------------

# Stock Samsung app ids, present on essentially every Tizen set. Used as a
# control: if one of these launches but yours does not, the WebSocket API is
# fine and the problem is your app (not installed, or a different id).
KNOWN_APPS = [("YouTube", "111299001912"), ("Netflix", "11101200001")]


def ask_yes_no(question: str) -> bool:
    while True:
        try:
            answer = input(f"  >>> {question} [y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if answer.startswith("y"):
            return True
        if answer.startswith("n"):
            return False


def probe_diagnose(tv: SamsungTVWS, app_id: str) -> None:
    """Separate 'this device refuses app launches' from 'your app is not there'.

    Both look identical from the API — the commands are accepted either way —
    so the only reliable instrument is your eyes on the screen.
    """
    header("D. Diagnosis — why did the launch fail?")
    print(
        "  Two very different problems look the same from the API, so this asks\n"
        "  you to watch the screen and answer. Take your time.\n"
    )

    # D1 — is the control channel alive at all?
    print("  Sending KEY_HOME. Watch the screen.\n")
    try:
        tv.send_key("KEY_HOME")
        time.sleep(3)
        control_ok = ask_yes_no("Did the screen react at all (home screen, menu, anything)?")
        record("Control channel", PASS if control_ok else FAIL,
               "KEY_HOME had a visible effect" if control_ok else "no visible reaction")
    except Exception as err:
        record("Control channel", FAIL, f"{type(err).__name__}: {err}")
        control_ok = False

    # D2 — can it launch an app that is definitely installed?
    known_ok = False
    known_name = ""
    for name, known_id in KNOWN_APPS:
        print(f"\n  Trying to launch {name} as a control, by every method.\n")
        if try_every_launch_method(tv, known_id, True):
            record(f"Launch {name}", PASS, "stock app launched")
            known_ok, known_name = True, name
            break
        record(f"Launch {name}", FAIL, "no method worked")

    # Conclusion
    header("Diagnosis")
    if not control_ok:
        print("  The control channel itself is not working — KEY_HOME did nothing.")
        print("  Pairing succeeded, so this is not authorisation. Check that the")
        print("  device is not in a power state that ignores input, and retry.")
        print("  Until KEY_HOME works, the launch result means nothing either way.")
        return

    if known_ok:
        print(f"  Local control WORKS on this device — {known_name} launched on command.")
        print(f"  So the WebSocket API is fine and the problem is specific to")
        print(f"  '{app_id}': either it is not installed here, or it is installed")
        print("  under a different id.")
        print("\n  Next: confirm the weather app is actually sideloaded on THIS device")
        print("  (it may only be on the S95), then re-run with the correct --app-id.")
        print("  This is good news for the migration — the mechanism is proven.")
        return

    print("  The control channel works (KEY_HOME responded) but no app would")
    print("  launch, including stock ones. That is this model refusing app")
    print("  launches over the local API — a real restriction, not your app.")
    print("\n  Fallback 1 from the plan applies and is now known to be viable:")
    print("  Wake-on-LAN to power on, then KEY_HOME plus a short navigation macro,")
    print("  since key input demonstrably works.")
    print("\n  Test the S95 before designing around this — it is the default target")
    print("  and may well behave differently.")


# --------------------------------------------------------------------------
# 6. Wake-on-LAN (optional)
# --------------------------------------------------------------------------

def probe_wol(ip: str, mac: str) -> bool:
    header("6. Wake-on-LAN")
    if send_magic_packet is None:
        record("Wake-on-LAN", SKIP, "wakeonlan not installed")
        return False
    if not mac:
        record("Wake-on-LAN", SKIP, "no MAC address — pass --mac aa:bb:cc:dd:ee:ff")
        return False

    print(
        "  Turn the TV OFF with the remote now, wait for the screen to go dark,\n"
        "  then press Enter here."
    )
    try:
        input("  > ")
    except (EOFError, KeyboardInterrupt):
        record("Wake-on-LAN", SKIP, "cancelled")
        return False

    send_magic_packet(mac)
    record("Magic packet sent", PASS, mac)

    print("  Waiting up to 30s for the TV to answer...")
    for _ in range(30):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        awake = sock.connect_ex((ip, 8001)) == 0 or sock.connect_ex((ip, 8002)) == 0
        sock.close()
        if awake:
            record("TV woke up", PASS, "responds after magic packet")
            return True
        time.sleep(1)

    record("TV woke up", FAIL, "no answer within 30s")
    print(
        "\n  Enable Settings > General > Network > Expert Settings > Power On with Mobile\n"
        "  (wording varies by model). On Wi-Fi this is less reliable than on Ethernet."
    )
    return False


# --------------------------------------------------------------------------
# Verdict
# --------------------------------------------------------------------------

def verdict(launched: bool, woke: bool | None, tested: bool = True) -> int:
    header("Verdict")
    failures = [k for k, (s, _) in results.items() if s == FAIL]

    if not tested:
        print("  INCONCLUSIVE — the probe never got far enough to try a launch.")
        print("  Nothing here says local control will not work; fix the step above")
        print("  and run again before drawing any conclusion about the migration.")
        if failures:
            print(f"\n  Failed steps: {', '.join(failures)}")
        return 2

    if launched:
        print("  Local app launch WORKS. Phase 2 can replace the SmartThings cloud call")
        print("  in python-utility/app.py with local control as planned.")
        if woke is False:
            print("\n  Wake-on-LAN did not work, though. The TV can be driven while awake but")
            print("  not woken — so the routine needs the set already on, or WoL needs")
            print("  enabling in the TV's network settings.")
        print("\n  Record for Phase 2:  TV_IP, TV_MAC, the app id the TV reported,")
        print(f"  and the token file. Reuse the client name \"{CLIENT_NAME}\" verbatim.")
        return 0

    print("  Local app launch DID NOT WORK on this set.")
    print("\n  This does not sink the migration — the sensor data path is unaffected and")
    print("  is where the recurring cost actually is. It means the TV-launch trigger")
    print("  needs a different design. In rough order of preference:")
    print("    1. Wake-on-LAN + send_key('KEY_HOME') and a short navigation macro.")
    print("    2. Leave the app resident on the TV and use WoL alone to wake the set.")
    print("    3. Drop the automatic launch; open the app from the remote.")
    if failures:
        print(f"\n  Failed steps: {', '.join(failures)}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ip", required=True, help="TV IP address")
    parser.add_argument("--mac", default="", help="TV MAC address (auto-detected if the TV reports it)")
    parser.add_argument("--app-id", default=DEFAULT_APP_ID, help=f"Tizen app id (default: {DEFAULT_APP_ID})")
    parser.add_argument("--token-file", default="tv-token.txt", help="where to persist the pairing token")
    parser.add_argument("--wol", action="store_true", help="also test Wake-on-LAN (asks you to turn the TV off)")
    parser.add_argument("--non-interactive", action="store_true",
                        help="never prompt; report API acceptance only and skip diagnosis")
    args = parser.parse_args()
    interactive = not args.non_interactive

    print(f"Phase 0 — local TV control probe against {args.ip}")

    if not probe_ports(args.ip):
        return verdict(False, None, tested=False)

    info = probe_device_info(args.ip)
    mac = args.mac or info.get("mac", "")

    tv = probe_pairing(args.ip, Path(args.token_file), info.get("token_auth", True))
    if tv is None:
        return verdict(False, None, tested=False)

    try:
        _found, stalled = probe_app_list(tv, args.app_id)

        if stalled:
            # A request the TV never answered can leave an unread reply in the
            # stream, which would desync the launch commands below. Start clean.
            try:
                tv.close()
            except Exception:
                pass
            tv = SamsungTVWS(
                host=args.ip,
                port=8002 if info.get("token_auth", True) else 8001,
                token_file=str(Path(args.token_file)),
                name=CLIENT_NAME,
                timeout=15,
            )
            tv.open()

        launched = probe_launch(tv, args.app_id, interactive)

        if not launched and interactive:
            probe_diagnose(tv, args.app_id)
    finally:
        try:
            tv.close()
        except Exception:
            pass

    woke = probe_wol(args.ip, mac) if args.wol else None
    return verdict(launched, woke)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)

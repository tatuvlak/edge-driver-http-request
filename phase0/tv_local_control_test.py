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
import time
import urllib.request
from pathlib import Path

try:
    from samsungtvws import SamsungTVWS
    from samsungtvws.exceptions import ConnectionFailure, HttpApiError, UnauthorizedError
except ImportError:
    sys.exit("Missing dependency. Run:  pip install -r requirements-phase0.txt")

try:
    from wakeonlan import send_magic_packet
except ImportError:
    send_magic_packet = None


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

def probe_app_list(tv: SamsungTVWS, app_id: str) -> bool:
    header("4. Installed applications")
    try:
        apps = tv.app_list()
    except Exception as err:
        record("List installed apps", FAIL, f"{type(err).__name__}: {err}")
        return False

    if not apps:
        record("List installed apps", WARN, "TV returned nothing — common on newer firmware")
        print("  Not fatal: launching by id can still work. Continuing.")
        return False

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
    return match is not None


# --------------------------------------------------------------------------
# 5. Launch — the decisive test
# --------------------------------------------------------------------------

def probe_launch(tv: SamsungTVWS, ip: str, app_id: str) -> bool:
    header("5. Launching the app (the decisive test)")
    print("  Watch the TV screen. Something should visibly happen within a few seconds.\n")

    launched = False

    for app_type in ("DEEP_LINK", "NATIVE_LAUNCH"):
        try:
            tv.run_app(app_id, app_type=app_type)
            time.sleep(4)
            record(f"WebSocket run_app ({app_type})", PASS, "command accepted")
            launched = True
            break
        except Exception as err:
            record(f"WebSocket run_app ({app_type})", FAIL, f"{type(err).__name__}: {err}")

    if not launched:
        try:
            tv.rest_app_run(app_id)
            time.sleep(4)
            record("REST app run", PASS, "command accepted")
            launched = True
        except (HttpApiError, Exception) as err:
            record("REST app run", FAIL, f"{type(err).__name__}: {err}")

    # "Accepted" is not "worked" — try to confirm independently.
    try:
        status = tv.rest_app_status(app_id)
        visible = status.get("visible")
        running = status.get("running")
        if visible or running:
            record("App confirmed running", PASS, f"visible={visible} running={running}")
        else:
            record("App confirmed running", WARN, f"visible={visible} running={running}")
    except Exception:
        record("App confirmed running", SKIP, "TV does not report status for this app")

    print(
        "\n  >>> Look at the TV now. Did the weather app actually open?\n"
        "      That observation matters more than any [PASS] above — some sets\n"
        "      acknowledge the command and then ignore it."
    )
    return launched


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
    args = parser.parse_args()

    print(f"Phase 0 — local TV control probe against {args.ip}")

    if not probe_ports(args.ip):
        return verdict(False, None, tested=False)

    info = probe_device_info(args.ip)
    mac = args.mac or info.get("mac", "")

    tv = probe_pairing(args.ip, Path(args.token_file), info.get("token_auth", True))
    if tv is None:
        return verdict(False, None, tested=False)

    try:
        probe_app_list(tv, args.app_id)
        launched = probe_launch(tv, args.ip, args.app_id)
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

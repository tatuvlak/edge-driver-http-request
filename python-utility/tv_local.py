"""Local Samsung TV control — no SmartThings, no cloud, no credentials.

Replaces the SmartThings `POST /v1/devices/{id}/commands` call that used to
launch the weather app. Samsung sets expose their own REST API on the LAN:

    POST https://<tv-ip>:8002/api/v2/applications/<app-id>

Phase 0 findings this is built on (see ../phase0/RESULTS.md):

* The REST launch is the only mechanism that works on 2022 sets. Both
  WebSocket `run_app` variants (`ed.apps.launch`, DEEP_LINK and NATIVE_LAUNCH)
  are accepted and silently ignored — they return cleanly having done nothing,
  which is precisely why they cannot be used as a fallback that detects its own
  failure.
* The REST path needs no pairing, no token and no WebSocket handshake. It is an
  unauthenticated POST on the local network, so none of the pairing-prompt or
  startup-event trouble applies here.
* Wake-on-LAN does not work on these displays over Wi-Fi, and is not needed: the
  SmartThings routine powers the display on before triggering this service. What
  matters instead is waiting for the TV's network stack to come up afterwards,
  which is what `wait_until_awake` is for.

The TV presents a self-signed certificate, so verification is disabled. That is
inherent to the device and the traffic never leaves the LAN.
"""

from __future__ import annotations

import logging
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import requests
import urllib3

# The TV's certificate is self-signed and cannot be verified; suppress the
# per-request warning rather than let it flood the service log.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

TV_REST_PORT = 8002
REQUEST_TIMEOUT = 8


@dataclass(frozen=True)
class Display:
    """One controllable display.

    `host` is the last known address and `mac` is the stable identity. Displays
    get their addresses by DHCP, so an address that worked yesterday may belong
    to something else today — the MAC is what actually says which set this is.
    """

    key: str  # 's95' | 'm7' — matches the Edge driver's target_device
    name: str  # human-readable, for logs and API responses
    host: str  # IP address or hostname on the LAN — last known, may be stale
    port: int = TV_REST_PORT
    mac: str = ""  # optional but strongly recommended: survives DHCP changes

    @property
    def configured(self) -> bool:
        return bool(self.host or self.mac)

    def at(self, host: str) -> "Display":
        """The same display, at a different address."""
        return Display(key=self.key, name=self.name, host=host, port=self.port, mac=self.mac)


def normalise_mac(mac: str) -> str:
    """Compare MACs without caring about case or separator."""
    return mac.lower().replace("-", "").replace(":", "").strip()


def device_info(host: str, port: int = TV_REST_PORT, timeout: float = 3.0) -> dict | None:
    """Read a Samsung display's unauthenticated /api/v2/ identity block."""
    try:
        response = requests.get(
            f"https://{host}:{port}/api/v2/", timeout=timeout, verify=False
        )
        if response.ok:
            return response.json().get("device", {})
    except (requests.RequestException, ValueError):
        pass
    return None


def find_by_mac(
    mac: str,
    subnet: str,
    port: int = TV_REST_PORT,
    connect_timeout: float = 1.0,
    workers: int = 64,
) -> str | None:
    """Scan a /24 for the display with this MAC. Returns its address, or None.

    Two stages, because a full identity fetch against 254 addresses would be
    slow: first a parallel TCP probe to find the handful of hosts with the API
    port open, then ask only those who they are. Identification is by MAC rather
    than by "something answered", so this cannot pick the wrong display.
    """
    wanted = normalise_mac(mac)
    if not wanted:
        return None

    prefix = subnet.rsplit(".", 1)[0]
    candidates = [f"{prefix}.{n}" for n in range(1, 255)]

    def port_open(host: str) -> str | None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(connect_timeout)
        try:
            return host if sock.connect_ex((host, port)) == 0 else None
        except OSError:
            return None
        finally:
            sock.close()

    logger.info("Scanning %s.0/24 for MAC %s", prefix, mac)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        listening = [h for h in pool.map(port_open, candidates) if h]

    logger.info("%d host(s) answering on port %d", len(listening), port)
    for host in listening:
        info = device_info(host, port)
        if info and normalise_mac(info.get("wifiMac", "")) == wanted:
            logger.info("Found %s at %s (%s)", mac, host, info.get("name", "?"))
            return host
    return None


def _api_url(display: Display, route: str) -> str:
    return f"https://{display.host}:{display.port}/api/v2/{route}"


def is_awake(display: Display, timeout: float = 2.0) -> bool:
    """True if the TV is answering on its API port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((display.host, display.port)) == 0
    except OSError:
        return False
    finally:
        sock.close()


def wait_until_awake(display: Display, timeout: float = 30.0, interval: float = 2.0) -> bool:
    """Block until the TV answers, or timeout expires.

    The routine that powers the display on returns before its network stack is
    up, so a launch fired immediately afterwards hits a set that is not
    listening yet. This is what makes the trigger reliable now that
    Wake-on-LAN is out of the picture.
    """
    deadline = time.monotonic() + timeout
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        if is_awake(display):
            if attempt > 1:
                logger.info("%s became reachable after %d checks", display.name, attempt)
            return True
        time.sleep(interval)
    logger.warning("%s did not answer on port %d within %.0fs", display.name, display.port, timeout)
    return False


def app_status(display: Display, app_id: str) -> dict | None:
    """Ask the TV about an app. None if it will not say.

    A real payload also confirms the id is one the TV recognises, which is worth
    distinguishing from a launch that was accepted and ignored.
    """
    try:
        response = requests.get(
            _api_url(display, f"applications/{app_id}"),
            timeout=REQUEST_TIMEOUT,
            verify=False,
        )
        if response.ok:
            return response.json()
        logger.debug("%s: app status returned HTTP %s", display.name, response.status_code)
    except (requests.RequestException, ValueError) as err:
        logger.debug("%s: app status unavailable (%s)", display.name, err)
    return None


def launch_app(
    display: Display,
    app_id: str,
    ready_timeout: float = 30.0,
    attempts: int = 3,
    retry_delay: float = 3.0,
) -> tuple[bool, dict]:
    """Launch an app on a display. Returns (ok, details).

    `verified` in the details distinguishes "the TV confirmed the app is on
    screen" from "the TV accepted the request and told us nothing useful".
    A launch is not reported as failed just because verification is unavailable
    — some models decline to report status — but the caller can see which it got.
    """
    details: dict = {"device": display.name, "host": display.host, "app_id": app_id}

    if not wait_until_awake(display, timeout=ready_timeout):
        details["error"] = f"{display.name} is not reachable on port {display.port}"
        details["hint"] = "The display may still be powering on, or is on another subnet."
        return False, details

    last_error = None
    for attempt in range(1, attempts + 1):
        details["attempts"] = attempt
        try:
            response = requests.post(
                _api_url(display, f"applications/{app_id}"),
                timeout=REQUEST_TIMEOUT,
                verify=False,
            )
        except requests.RequestException as err:
            last_error = str(err)
            logger.warning("%s: launch attempt %d failed to send (%s)", display.name, attempt, err)
            time.sleep(retry_delay)
            continue

        if not response.ok:
            last_error = f"HTTP {response.status_code}"
            logger.warning("%s: launch attempt %d returned %s", display.name, attempt, last_error)
            time.sleep(retry_delay)
            continue

        # Accepted. Give the app a moment to come up, then try to confirm — the
        # POST succeeding is not by itself evidence that anything happened.
        time.sleep(2)
        status = app_status(display, app_id)
        if status and (status.get("visible") or status.get("running")):
            logger.info("%s: '%s' confirmed running", display.name, app_id)
            details["verified"] = True
            return True, details

        if attempt < attempts:
            logger.info(
                "%s: launch accepted but not confirmed on attempt %d, retrying", display.name, attempt
            )
            time.sleep(retry_delay)
            continue

        # Out of retries but the TV never refused us. Report success without
        # claiming confirmation, rather than failing something that likely worked.
        logger.info("%s: '%s' launch accepted, could not confirm", display.name, app_id)
        details["verified"] = False
        details["note"] = "TV accepted the launch but did not report the app as running"
        return True, details

    details["error"] = last_error or "launch failed"
    return False, details

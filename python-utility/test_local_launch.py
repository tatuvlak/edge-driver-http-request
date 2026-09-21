"""Self-contained tests for local TV launching — no real TV needed.

Spins up a fake Samsung display (self-signed TLS on a random port, the same
/api/v2/applications/{id} surface a real set exposes) and drives both the
tv_local module and the Flask endpoint the Edge driver calls.

    python test_local_launch.py

Requires flask, requests and openssl on PATH. Exits non-zero on failure.
"""
import json
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, "/home/user/edge-driver-http-request/python-utility")
import tv_local

APP_ID = "tvweather1.tvweather"

# --- a self-signed cert, like every Samsung TV serves on 8002 -----------------
tmp = Path(tempfile.mkdtemp())
cert, key = tmp / "c.pem", tmp / "k.pem"
subprocess.run(
    ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", str(key),
     "-out", str(cert), "-days", "1", "-nodes", "-subj", "/CN=faketv"],
    check=True, capture_output=True,
)


class FakeTV(BaseHTTPRequestHandler):
    running = False
    launch_posts = 0
    report_status = True          # some models refuse to report; toggled per-case
    fail_launch_with = None       # e.g. 404

    def _json(self, code, body):
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == f"/api/v2/applications/{APP_ID}":
            if not FakeTV.report_status:
                return self._json(404, {})
            return self._json(200, {"visible": FakeTV.running, "running": FakeTV.running})
        self._json(404, {})

    def do_POST(self):
        if self.path == f"/api/v2/applications/{APP_ID}":
            FakeTV.launch_posts += 1
            if FakeTV.fail_launch_with:
                return self._json(FakeTV.fail_launch_with, {})
            FakeTV.running = True     # the app opens, as on the real M7
            return self._json(200, {})
        self._json(404, {})

    def log_message(self, *a):
        pass


ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
srv = HTTPServer(("127.0.0.1", 0), FakeTV)
srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

tv = tv_local.Display(key="test", name="Fake TV", host="127.0.0.1", port=port)
off = tv_local.Display(key="off", name="Powered-off TV", host="127.0.0.1", port=1)

failures = []


def check(label, condition, detail=""):
    print(f"  {'ok ' if condition else 'BAD'} {label}{(' — ' + str(detail)) if detail else ''}")
    if not condition:
        failures.append(label)


print("\nreachability")
check("awake TV detected", tv_local.is_awake(tv))
check("closed port reported not awake", not tv_local.is_awake(off))

print("\nhappy path (M7 behaviour: REST launch works, status confirms)")
FakeTV.running, FakeTV.launch_posts, FakeTV.report_status, FakeTV.fail_launch_with = False, 0, True, None
ok, details = tv_local.launch_app(tv, APP_ID, ready_timeout=5)
check("launch reported success", ok, details)
check("verified against TV status", details.get("verified") is True)
check("exactly one POST needed", FakeTV.launch_posts == 1, FakeTV.launch_posts)

print("\nTV accepts launch but will not report status")
FakeTV.running, FakeTV.launch_posts, FakeTV.report_status = False, 0, False
t0 = time.monotonic()
ok, details = tv_local.launch_app(tv, APP_ID, ready_timeout=5, attempts=2, retry_delay=0.2)
check("still reported success", ok, details)
check("but NOT claimed as verified", details.get("verified") is False)
check("retried before giving up", FakeTV.launch_posts == 2, FakeTV.launch_posts)

print("\nTV rejects the launch (bad app id)")
FakeTV.running, FakeTV.launch_posts, FakeTV.report_status, FakeTV.fail_launch_with = False, 0, True, 404
ok, details = tv_local.launch_app(tv, APP_ID, ready_timeout=5, attempts=2, retry_delay=0.2)
check("reported failure", not ok, details)
check("error explains why", "404" in str(details.get("error")), details.get("error"))

print("\ndisplay not reachable (readiness wait expires)")
t0 = time.monotonic()
ok, details = tv_local.launch_app(off, APP_ID, ready_timeout=3, attempts=2, retry_delay=0.2)
elapsed = time.monotonic() - t0
check("reported failure", not ok)
check("waited for readiness before giving up", 2.5 <= elapsed <= 8, f"{elapsed:.1f}s")
check("error names reachability", "not reachable" in str(details.get("error")), details.get("error"))



# --------------------------------------------------------------------------
# The Flask endpoint the Edge driver actually calls
# --------------------------------------------------------------------------

import app as flaskapp  # noqa: E402

# Hand the endpoint section a clean fake TV: the module tests above deliberately
# leave it rejecting launches.
FakeTV.running = False
FakeTV.launch_posts = 0
FakeTV.report_status = True
FakeTV.fail_launch_with = None

flaskapp.config.TV_HOST_S95 = "127.0.0.1"
flaskapp.config.TV_HOST_M7 = ""
flaskapp.config.TV_APP_ID = APP_ID
flaskapp.get_displays = lambda: {
    's95': tv_local.Display('s95', 'S95 TV', '127.0.0.1', port),
    'm7': tv_local.Display('m7', 'M7 Monitor', flaskapp.config.TV_HOST_M7, port),
}

c = flaskapp.app.test_client()
fails = failures
def check(label, cond, detail=""):
    print(f"  {'ok ' if cond else 'BAD'} {label}{(' — '+str(detail)) if detail else ''}")
    if not cond: fails.append(label)

fails = []
def check(label, cond, detail=""):
    print(f"  {'ok ' if cond else 'BAD'} {label}{(' — '+str(detail)) if detail else ''}")
    if not cond: fails.append(label)

print("\nthe Edge driver's actual payload")
r = c.post("/launch-tv-app", json={"action":"launch","device_id":"x","target_device":"s95","timestamp":1})
check("HTTP 200", r.status_code == 200, r.status_code)
check("success true", r.get_json().get("success") is True, r.get_json())

print("\ndefaults to S95 when target_device is absent")
FakeTV.running = False
r = c.post("/launch-tv-app", json={"action":"launch"})
check("HTTP 200", r.status_code == 200, r.status_code)
check("routed to S95", r.get_json().get("device") == "S95 TV", r.get_json().get("device"))

print("\nunconfigured display is a clear 500, not a crash")
r = c.post("/launch-tv-app", json={"target_device":"m7"})
check("HTTP 500", r.status_code == 500, r.status_code)
check("hint names the env var", "TV_HOST_M7" in json.dumps(r.get_json()), r.get_json())

print("\nunknown target is rejected as a bad request")
r = c.post("/launch-tv-app", json={"target_device":"nonsense"})
check("HTTP 400", r.status_code == 400, r.status_code)
check("lists known devices", r.get_json().get("known_devices") == ["m7","s95"], r.get_json())

print("\nempty body still works (driver sends none on some paths)")
FakeTV.running = False
r = c.post("/launch-tv-app")
check("HTTP 200", r.status_code == 200, r.status_code)

print("\ndiagnostics")
r = c.get("/health");   check("/health ok", r.status_code == 200 and "local" in json.dumps(r.get_json()), r.get_json())
r = c.get("/displays"); check("/displays reports reachability", r.get_json()["displays"]["s95"]["reachable"] is True, r.get_json())
r = c.get("/config");   check("/config has no SmartThings auth fields", "auth_method" not in r.get_json(), r.get_json())

print("\n" + ("FAILURES: " + ", ".join(fails) if fails else "all checks passed"))
sys.exit(1 if fails else 0)

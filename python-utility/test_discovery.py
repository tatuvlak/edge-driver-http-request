"""Discovery: can a moved display be found again, and only the right one?"""
import json, ssl, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, "/home/user/edge-driver-http-request/python-utility")
import tv_local

tmp = Path(tempfile.mkdtemp()); cert, key = tmp/"c.pem", tmp/"k.pem"
subprocess.run(["openssl","req","-x509","-newkey","rsa:2048","-keyout",str(key),"-out",str(cert),
                "-days","1","-nodes","-subj","/CN=faketv"], check=True, capture_output=True)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(str(cert), str(key))

def make_tv(mac, name):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"device": {"wifiMac": mac, "name": name}}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)
        def log_message(self,*a): pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]

S95_MAC, M7_MAC = "F0:70:4F:32:BF:DA", "54:44:A3:5C:4B:16"
p_s95 = make_tv(S95_MAC, "S95 TV")
p_m7  = make_tv(M7_MAC, "M7 Monitor")

fails = []
def check(l, c, d=""):
    print(f"  {'ok ' if c else 'BAD'} {l}{(' — '+str(d)) if d else ''}")
    if not c: fails.append(l)

print("\nMAC normalisation")
check("case and separators ignored",
      tv_local.normalise_mac("F0-70-4F-32-BF-DA") == tv_local.normalise_mac("f0:70:4f:32:bf:da"))

print("\ndevice identity")
info = tv_local.device_info("127.0.0.1", p_s95)
check("reads wifiMac", info and info["wifiMac"] == S95_MAC, info)
check("unreachable host returns None", tv_local.device_info("127.0.0.1", 1) is None)

print("\nfinding a display by MAC")
# Scan 127.0.0.x on the S95's port: only that port serves the S95 identity.
found = tv_local.find_by_mac(S95_MAC, "127.0.0.1", port=p_s95, connect_timeout=0.3)
check("finds the S95", found == "127.0.0.1", found)

print("\nit will not return the wrong display")
# Ask for the S95's MAC on the port where only the M7 answers.
wrong = tv_local.find_by_mac(S95_MAC, "127.0.0.1", port=p_m7, connect_timeout=0.3)
check("a different display is not accepted", wrong is None, wrong)
check("an unknown MAC finds nothing",
      tv_local.find_by_mac("00:00:00:00:00:01", "127.0.0.1", port=p_s95, connect_timeout=0.3) is None)
check("an empty MAC finds nothing", tv_local.find_by_mac("", "127.0.0.1", port=p_s95) is None)

print("\nresolution through the app, with caching")
import app as flaskapp
cache = str(Path(tempfile.mkdtemp())/"c.json")
flaskapp.config.DISPLAY_CACHE_PATH = cache

stale = tv_local.Display('s95', 'S95 TV', '127.0.0.2', p_s95, S95_MAC)  # wrong address
resolved, err = flaskapp.resolve_display(stale)
check("stale address is recovered by MAC", err is None and resolved.host == "127.0.0.1", (resolved.host, err))
check("and remembered for next time", json.loads(Path(cache).read_text()).get("s95") == "127.0.0.1")

live = tv_local.Display('s95', 'S95 TV', '127.0.0.1', p_s95, S95_MAC)
resolved, err = flaskapp.resolve_display(live)
check("a working address is used as-is", err is None and resolved.host == "127.0.0.1")

no_mac = tv_local.Display('m7', 'M7 Monitor', '127.0.0.2', p_m7, "")
resolved, err = flaskapp.resolve_display(no_mac)
check("without a MAC it explains why it cannot look", err and "MAC" in err, err)

print("\n" + ("FAILURES: " + ", ".join(fails) if fails else "all checks passed"))
sys.exit(1 if fails else 0)

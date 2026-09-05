"""
TV App Launcher Utility

Receives HTTP requests from the SmartThings Edge Driver and launches the weather
app on a Samsung display over the LAN, using the display's own REST API.

The launch used to go out through the SmartThings cloud API, which becomes a paid
subscription in October 2026. The Edge driver's contract is unchanged — it still
POSTs to /launch-tv-app — only the implementation behind it moved local, so
existing routines keep working untouched. See ../phase0/RESULTS.md.
"""

from flask import Flask, request, jsonify, redirect, session
import requests
import os
import json
import hmac
import logging
import time
from functools import wraps
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

import tv_local
import weather_store

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
class Config:
    # SmartThings API configuration
    ST_API_BASE_URL = "https://api.smartthings.com/v1"
    ST_PAT = os.environ.get('SMARTTHINGS_PAT', '')  # Personal Access Token (fallback only)
    
    # OAuth configuration
    ST_CLIENT_ID = os.environ.get('ST_CLIENT_ID', '')
    ST_CLIENT_SECRET = os.environ.get('ST_CLIENT_SECRET', '')
    ST_REFRESH_TOKEN = os.environ.get('ST_REFRESH_TOKEN', '')
    
    # OAuth token storage
    TOKEN_FILE = os.environ.get('TOKEN_FILE', '/app/data/oauth_tokens.json')
    
    # OAuth callback configuration
    # Use external callback page (GitHub Pages) since this service runs on local NAS
    OAUTH_REDIRECT_URI = os.environ.get('OAUTH_REDIRECT_URI', 'https://tatuvlak.github.io/tv-weather-oauth/callback.html')
    # Note: Authorization code from external callback must be manually entered via /oauth/token endpoint
    
    # TV/Monitor configuration — local control (no SmartThings)
    # Addresses on the LAN. Give each display a DHCP reservation so these are stable.
    TV_HOST_S95 = os.environ.get('TV_HOST_S95', '')
    TV_HOST_M7 = os.environ.get('TV_HOST_M7', '')

    # MAC addresses — the stable identity of each display. With these set, a
    # display that moves to a new DHCP address is found again automatically;
    # without them, a lease change breaks the launch until TV_HOST_* is edited.
    TV_MAC_S95 = os.environ.get('TV_MAC_S95', '')
    TV_MAC_M7 = os.environ.get('TV_MAC_M7', '')
    # Where discovered addresses are remembered between restarts.
    DISPLAY_CACHE_PATH = os.environ.get('DISPLAY_CACHE_PATH', '/app/data/display_ips.json')
    # Subnet to scan when a display has moved. Defaults to the one implied by
    # its last known address, which is right on a normal flat home network.
    TV_SCAN_SUBNET = os.environ.get('TV_SCAN_SUBNET', '')

    # How long to wait for a display to answer after the routine powers it on,
    # and how many times to retry the launch itself.
    TV_READY_TIMEOUT = float(os.environ.get('TV_READY_TIMEOUT', 30))
    TV_LAUNCH_ATTEMPTS = int(os.environ.get('TV_LAUNCH_ATTEMPTS', 3))

    # Legacy SmartThings device IDs — no longer used to launch the app, kept only
    # for the /device-status endpoint until that is removed too.
    TV_DEVICE_ID_S95 = os.environ.get('TV_DEVICE_ID_S95', os.environ.get('TV_DEVICE_ID', ''))
    TV_DEVICE_ID_M7 = os.environ.get('TV_DEVICE_ID_M7', '')

    TV_APP_ID = os.environ.get('TV_APP_ID', '')  # Your weather app ID
    
    # Weather data hub
    WEATHER_DB_PATH = os.environ.get('WEATHER_DB_PATH', '/app/data/weather.db')
    # A reading older than this is served with stale=true so the displays can
    # say so rather than quietly showing an hour-old number as if it were now.
    WEATHER_STALE_AFTER = float(os.environ.get('WEATHER_STALE_AFTER', 120))
    WEATHER_RETENTION_DAYS = float(os.environ.get('WEATHER_RETENTION_DAYS', 30))

    # Three separate tokens, because these have very different blast radii.
    # The read token ships inside the .wgt on the TV, so it must never be the
    # one that can forge sensor readings or command hardware.
    INGEST_TOKEN = os.environ.get('INGEST_TOKEN', '')   # write: the ESP32 only
    READ_TOKEN = os.environ.get('READ_TOKEN', '')       # read: TV and phone apps
    ACTION_TOKEN = os.environ.get('ACTION_TOKEN', '')   # act: the Edge driver

    # Server configuration
    PORT = int(os.environ.get('PORT', 5000))
    HOST = os.environ.get('HOST', '0.0.0.0')
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

config = Config()


def get_displays():
    """The displays this service can drive, keyed by the Edge driver's target_device.

    Addresses come from config, then from whatever discovery last found — the
    cached value wins when config has gone stale, which is the usual case after
    a DHCP lease changes.
    """
    cache = _load_display_cache()
    return {
        's95': tv_local.Display(
            key='s95', name='S95 TV',
            host=cache.get('s95') or config.TV_HOST_S95, mac=config.TV_MAC_S95,
        ),
        'm7': tv_local.Display(
            key='m7', name='M7 Monitor',
            host=cache.get('m7') or config.TV_HOST_M7, mac=config.TV_MAC_M7,
        ),
    }


def _load_display_cache():
    try:
        path = Path(config.DISPLAY_CACHE_PATH)
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        logger.warning("Could not read the display cache; ignoring it", exc_info=True)
    return {}


def _remember_display(key, host):
    try:
        path = Path(config.DISPLAY_CACHE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        cache = _load_display_cache()
        cache[key] = host
        path.write_text(json.dumps(cache, indent=2))
        logger.info("Remembered %s at %s", key, host)
    except Exception:
        # Losing the cache costs a rescan next time, nothing more.
        logger.warning("Could not write the display cache", exc_info=True)


def resolve_display(display):
    """Return the display at an address that answers, rediscovering if needed.

    The fast path is the address we already have. Only when that stops
    answering do we scan, and only when a MAC is configured to identify the
    result — otherwise we could just as easily point at the neighbour's TV.
    """
    if display.host and tv_local.is_awake(display, timeout=1.5):
        return display, None

    if not display.mac:
        hint = ('No MAC configured, so a moved display cannot be found again. '
                f'Set TV_MAC_{display.key.upper()} in .env, or give it a DHCP reservation.')
        return display, hint

    subnet = config.TV_SCAN_SUBNET or display.host
    if not subnet:
        return display, 'No address or subnet to scan from; set TV_SCAN_SUBNET.'

    logger.info("%s is not at %s any more; looking for it by MAC", display.name, display.host or '?')
    found = tv_local.find_by_mac(display.mac, subnet, port=display.port)
    if not found:
        return display, f'{display.name} was not found on {subnet.rsplit(".", 1)[0]}.0/24'

    _remember_display(display.key, found)
    return display.at(found), None

def _token_ok(expected):
    """Check the request's bearer token against `expected`.

    An unset token means that endpoint is unauthenticated. That is deliberate
    for the action token: the Edge driver currently sends no credentials, and
    turning this on before the driver is republished would break the routine.
    Ingest and read are new endpoints with no such constraint, so they should
    always have tokens set.
    """
    if not expected:
        return True
    supplied = request.headers.get('Authorization', '')
    if supplied.startswith('Bearer '):
        supplied = supplied[7:]
    else:
        supplied = request.headers.get('X-Auth-Token', '')
    # compare_digest over a constant-time comparison of equal-length strings
    return hmac.compare_digest(supplied, expected)


def require_token(get_expected):
    """Guard a route with one of the configured tokens."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not _token_ok(get_expected()):
                return jsonify({'success': False, 'error': 'unauthorized'}), 401
            return view(*args, **kwargs)
        return wrapper
    return decorator


try:
    weather_store.init(config.WEATHER_DB_PATH)
except Exception:
    # A broken store must not stop the service launching apps — that path is
    # independent and is the one a routine depends on.
    logger.exception("Could not initialise the weather store at %s", config.WEATHER_DB_PATH)


class SmartThingsAPI:
    """SmartThings API client with OAuth support"""
    
    def __init__(self, use_oauth=True):
        self.use_oauth = use_oauth
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = None
        
        # Load tokens from file if they exist
        if use_oauth:
            self._load_tokens()
            # If we have a refresh token but no valid access token, refresh immediately
            if self.refresh_token and (not self.access_token or self.is_token_expired()):
                logger.info("Initial token refresh on startup")
                self.refresh_oauth_token()
    
    def _load_tokens(self):
        """Load OAuth tokens from file"""
        try:
            token_file = Path(config.TOKEN_FILE)
            if token_file.exists():
                with open(token_file, 'r') as f:
                    data = json.load(f)
                    self.access_token = data.get('access_token')
                    self.refresh_token = data.get('refresh_token')
                    self.token_expires_at = data.get('expires_at')
                    self._token_created_at = data.get('created_at', datetime.now().timestamp())
                    logger.info("OAuth tokens loaded from file")
                    logger.info(f"Loaded: has_access_token={bool(self.access_token)}, has_refresh_token={bool(self.refresh_token)}")
            else:
                # Try to use refresh token from environment if file doesn't exist
                if config.ST_REFRESH_TOKEN:
                    self.refresh_token = config.ST_REFRESH_TOKEN
                    logger.info("Using refresh token from environment")
        except Exception as e:
            logger.error(f"Failed to load tokens from file: {e}")
    
    def _save_tokens(self):
        """Save OAuth tokens to file"""
        try:
            token_file = Path(config.TOKEN_FILE)
            token_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Store token creation timestamp for age tracking
            self._token_created_at = datetime.now().timestamp()
            
            data = {
                'access_token': self.access_token,
                'refresh_token': self.refresh_token,
                'expires_at': self.token_expires_at,
                'created_at': self._token_created_at,
                'updated_at': datetime.now().isoformat()
            }
            
            with open(token_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("OAuth tokens saved to file")
            logger.info(f"Saved: has_access_token={bool(self.access_token)}, has_refresh_token={bool(self.refresh_token)}")
        except Exception as e:
            logger.error(f"Failed to save tokens to file: {e}")
    
    def get_headers(self):
        """Get API request headers"""
        if self.use_oauth:
            if not self.access_token or self.is_token_expired():
                logger.info("Token missing or expired, refreshing...")
                self.refresh_oauth_token()
            token = self.access_token
        else:
            token = config.ST_PAT
            
        if not token:
            raise ValueError("No authentication token available")
            
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    
    def is_token_expired(self):
        """Check if current OAuth token is expired"""
        if not self.token_expires_at:
            return True
        # Add 5-minute buffer before expiration
        buffer_seconds = 300
        return datetime.now().timestamp() >= (self.token_expires_at - buffer_seconds)
    
    def refresh_oauth_token(self):
        """Refresh OAuth access token using refresh token"""
        if not self.refresh_token:
            logger.error("No refresh token available")
            return False
            
        if not config.ST_CLIENT_ID:
            logger.error("OAuth client ID not configured")
            return False
        
        # Calculate token age for logging
        if hasattr(self, '_token_created_at'):
            token_age_hours = (datetime.now().timestamp() - self._token_created_at) / 3600
            logger.info(f"Attempting token refresh (token age: {token_age_hours:.2f} hours)")
        else:
            logger.info("Attempting token refresh")
        
        logger.info(f"Token status: has_refresh_token={bool(self.refresh_token)}")
            
        # SmartThings uses /oauth/token endpoint
        token_url = "https://api.smartthings.com/oauth/token"
        
        # Prepare form data
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }
        
        # Use Basic Auth if client_secret is available
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        auth = None
        if config.ST_CLIENT_SECRET:
            # Use HTTP Basic Authentication with client credentials
            auth = (config.ST_CLIENT_ID, config.ST_CLIENT_SECRET)
            logger.info("Using Basic Auth for token refresh")
        else:
            # Include client_id in body if no client_secret
            data['client_id'] = config.ST_CLIENT_ID
            logger.info("Using client_id in body for token refresh")
        
        try:
            logger.info("Refreshing OAuth token...")
            response = requests.post(
                token_url,
                data=data,
                headers=headers,
                auth=auth,
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"Token refresh failed: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False
            
            token_data = response.json()
            self.access_token = token_data.get('access_token')
            
            # Calculate expiration time
            expires_in = token_data.get('expires_in', 86400)  # Default 24 hours
            self.token_expires_at = datetime.now().timestamp() + expires_in
            
            # Preserve existing refresh_token if new one not provided
            # SmartThings typically doesn't return refresh_token on refresh flow
            new_refresh_token = token_data.get('refresh_token')
            if new_refresh_token:
                self.refresh_token = new_refresh_token
                logger.info("Refresh token updated with new value")
            else:
                logger.info("Preserving existing refresh_token (not returned in response)")
            
            # Validate we have a refresh token
            if not self.refresh_token:
                logger.warning("No refresh_token available - tokens may not be refreshable")
            
            # Save tokens to file
            self._save_tokens()
            
            logger.info(f"OAuth token refreshed successfully (expires in {expires_in}s)")
            logger.info(f"Token status: has_access_token={bool(self.access_token)}, has_refresh_token={bool(self.refresh_token)}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to refresh OAuth token: {e}")
            return False
    
    def launch_app(self, device_id, app_id):
        """Launch app on Samsung TV - sends power on + app launch commands"""
        url = f"{config.ST_API_BASE_URL}/devices/{device_id}/commands"
        
        # Send both power on and app launch commands
        # Based on your existing tv-app-launch.py implementation
        payload = {
            "commands": [
                {
                    "component": "main",
                    "capability": "switch",
                    "command": "on"
                },
                {
                    "component": "main",
                    "capability": "custom.launchapp",
                    "command": "launchApp",
                    "arguments": [app_id]
                }
            ]
        }
        
        try:
            # Try with current token
            response = requests.post(
                url,
                json=payload,
                headers=self.get_headers(),
                timeout=10
            )
            
            # If unauthorized and using OAuth, try refreshing token
            if response.status_code == 401 and self.use_oauth:
                logger.info("Token expired (401), attempting to refresh")
                if self.refresh_oauth_token():
                    response = requests.post(
                        url,
                        json=payload,
                        headers=self.get_headers(),
                        timeout=10
                    )
            
            response.raise_for_status()
            logger.info(f"Successfully launched app {app_id} on device {device_id}")
            return True, response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to launch app: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return False, str(e)
    
    def get_device_status(self, device_id):
        """Get device status"""
        url = f"{config.ST_API_BASE_URL}/devices/{device_id}/status"
        
        try:
            response = requests.get(
                url,
                headers=self.get_headers(),
                timeout=10
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get device status: {e}")
            return None

# Initialize SmartThings API client
# Uses OAuth by default, falls back to PAT if OAuth is not configured
use_oauth = bool(config.ST_CLIENT_ID and (config.ST_REFRESH_TOKEN or Path(config.TOKEN_FILE).exists()))
if not use_oauth and not config.ST_PAT:
    logger.info("No SmartThings credentials configured - fine, launching does not need them")
elif use_oauth:
    logger.info("SmartThings OAuth configured (only used by the legacy /device-status endpoint)")
else:
    logger.info("SmartThings PAT configured (only used by the legacy /device-status endpoint)")
    
st_api = SmartThingsAPI(use_oauth=use_oauth)

# Set Flask secret key for sessions
app.secret_key = config.SECRET_KEY

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        row = weather_store.latest(config.WEATHER_DB_PATH)
        weather = {
            'has_readings': row is not None,
            'age_seconds': round(time.time() - row['recorded_at'], 1) if row else None,
        }
    except Exception as err:
        weather = {'error': str(err)}

    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '3.1.0',
        'launch_method': 'local REST (no SmartThings)',
        'weather': weather,
    })


@app.route('/displays', methods=['GET'])
def displays_status():
    """Which displays are configured, and are they answering right now?

    Setup and troubleshooting aid: distinguishes 'wrong address in .env' from
    'display is off', which otherwise look the same from a failed launch.
    Add ?rediscover=1 to hunt for anything unreachable by MAC.
    """
    rediscover = request.args.get('rediscover') == '1'
    report = {}
    for key, display in get_displays().items():
        entry = {
            'name': display.name,
            'host': display.host or None,
            'mac': display.mac or None,
            'configured': display.configured,
            'reachable': bool(display.host) and tv_local.is_awake(display),
        }
        if rediscover and not entry['reachable'] and display.mac:
            resolved, err = resolve_display(display)
            entry['rediscovered_at'] = resolved.host if not err else None
            entry['reachable'] = not err
            if err:
                entry['error'] = err
        if not display.mac:
            entry['warning'] = (
                f'No TV_MAC_{key.upper()} set — if this display gets a new DHCP '
                'address, the launch will fail until .env is edited.'
            )
        report[key] = entry
    return jsonify({'displays': report, 'app_id': config.TV_APP_ID or None})

@app.route('/oauth/authorize', methods=['GET'])
def oauth_authorize():
    """Get OAuth authorization URL (manual flow for local NAS deployment)"""
    if not config.ST_CLIENT_ID:
        return jsonify({
            'success': False,
            'error': 'OAuth client ID not configured'
        }), 500
    
    # Build authorization URL
    auth_url = "https://api.smartthings.com/oauth/authorize"
    params = {
        'client_id': config.ST_CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': config.OAUTH_REDIRECT_URI,
        'scope': 'r:devices:* x:devices:*'  # Adjust scopes as needed
    }
    
    # Create query string
    from urllib.parse import urlencode
    query = urlencode(params)
    full_url = f"{auth_url}?{query}"
    
    logger.info(f"Authorization URL requested")
    
    # Return JSON with instructions for manual OAuth flow
    return jsonify({
        'success': True,
        'authorization_url': full_url,
        'instructions': [
            '1. Open the authorization_url in your browser',
            '2. Log in with your SmartThings account and authorize',
            '3. You will be redirected to the callback page with the code',
            '4. Copy the authorization code from the callback page',
            '5. POST the code to /oauth/token endpoint: {"code": "your-code"}'
        ],
        'callback_url': config.OAUTH_REDIRECT_URI,
        'token_endpoint': '/oauth/token'
    })

@app.route('/oauth/token', methods=['POST'])
def oauth_token_exchange():
    """Exchange authorization code for tokens (manual flow)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body must be JSON'
            }), 400
        
        code = data.get('code')
        if not code:
            return jsonify({
                'success': False,
                'error': 'Authorization code is required in request body: {"code": "your-code"}'
            }), 400
        
        logger.info("Exchanging authorization code for tokens...")
        
        # Exchange code for tokens
        token_url = "https://api.smartthings.com/oauth/token"
        token_data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': config.OAUTH_REDIRECT_URI
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        auth = None
        if config.ST_CLIENT_SECRET:
            auth = (config.ST_CLIENT_ID, config.ST_CLIENT_SECRET)
        else:
            token_data['client_id'] = config.ST_CLIENT_ID
        
        response = requests.post(
            token_url,
            data=token_data,
            headers=headers,
            auth=auth,
            timeout=10
        )
        
        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.status_code}")
            logger.error(f"Response: {response.text}")
            return jsonify({
                'success': False,
                'error': f'Token exchange failed: {response.text}'
            }), 400
        
        token_response = response.json()
        
        # Update API client with new tokens
        st_api.access_token = token_response.get('access_token')
        st_api.refresh_token = token_response.get('refresh_token')
        
        expires_in = token_response.get('expires_in', 86400)
        st_api.token_expires_at = datetime.now().timestamp() + expires_in
        
        # Enable OAuth mode now that we have tokens
        st_api.use_oauth = True
        
        # Save tokens
        st_api._save_tokens()
        
        logger.info("OAuth authorization successful! Tokens saved.")
        
        return jsonify({
            'success': True,
            'message': 'OAuth authorization successful! Tokens saved.',
            'expires_in': expires_in,
            'expires_at': datetime.fromtimestamp(st_api.token_expires_at).isoformat()
        })
        
    except Exception as e:
        logger.exception("Failed to exchange authorization code for tokens")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/launch-tv-app', methods=['POST'])
@require_token(lambda: config.ACTION_TOKEN)
def launch_tv_app():
    """Launch the weather app on a display — called by the Edge Driver.

    The request contract is unchanged from the SmartThings implementation, so
    the driver and any existing routines need no modification. The routine is
    expected to have powered the display on already; this waits for it to come
    up rather than trying to wake it.
    """
    try:
        data = request.get_json(silent=True) or {}
        target_device = data.get('target_device') or data.get('target') or 's95'

        displays = get_displays()
        display = displays.get(target_device)
        if display is None:
            return jsonify({
                'success': False,
                'error': f"Unknown target_device '{target_device}'",
                'known_devices': sorted(displays),
            }), 400

        logger.info("Launch requested on %s (%s)", display.name, target_device)

        if not display.configured:
            return jsonify({
                'success': False,
                'error': f'No address or MAC configured for {display.name}',
                'hint': f'Set TV_HOST_{target_device.upper()} (and ideally TV_MAC_{target_device.upper()}) in .env',
            }), 500

        # The display may have taken a new DHCP address since we last spoke to
        # it; find it again by MAC rather than failing.
        display, resolve_error = resolve_display(display)
        if resolve_error:
            return jsonify({
                'success': False,
                'error': f'Could not locate {display.name}',
                'hint': resolve_error,
            }), 502

        if not config.TV_APP_ID:
            return jsonify({
                'success': False,
                'error': 'TV_APP_ID not configured',
            }), 500

        success, details = tv_local.launch_app(
            display,
            config.TV_APP_ID,
            ready_timeout=config.TV_READY_TIMEOUT,
            attempts=config.TV_LAUNCH_ATTEMPTS,
        )

        payload = {
            'success': success,
            'device': display.name,
            'timestamp': datetime.now().isoformat(),
            'details': details,
        }

        if success:
            payload['message'] = f'Weather app launched on {display.name}'
            return jsonify(payload)

        payload['error'] = details.get('error', 'launch failed')
        return jsonify(payload), 502
    except Exception as e:
        logger.exception("Unexpected error while launching TV app")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Pruning is done on the ingest path rather than a background thread, because
# gunicorn runs several workers and a timer in each would just multiply the work.
# Once an hour is plenty at one reading every 30 seconds.
_PRUNE_INTERVAL = 3600.0
_last_prune = 0.0


def _prune_if_due():
    global _last_prune
    now = time.time()
    if now - _last_prune < _PRUNE_INTERVAL:
        return
    _last_prune = now
    try:
        weather_store.prune(config.WEATHER_DB_PATH, config.WEATHER_RETENTION_DAYS)
    except Exception:
        # Never fail an ingest over housekeeping; the reading is the point.
        logger.exception("Pruning old readings failed")


@app.route('/ingest', methods=['POST'])
@require_token(lambda: config.INGEST_TOKEN)
def ingest_reading():
    """Accept a reading from the weather station.

    The ESP32 posts here every 30 seconds, in the same loop that already updates
    its Matter clusters. This is the path that replaces reading the sensor back
    out of the SmartThings cloud.
    """
    try:
        reading = weather_store.validate(request.get_json(silent=True))
    except weather_store.ValidationError as err:
        # Say exactly what was wrong: this is read off a serial console with no
        # debugger attached.
        logger.warning("Rejected reading: %s", err)
        return jsonify({'success': False, 'error': str(err)}), 400

    try:
        recorded_at = weather_store.record(config.WEATHER_DB_PATH, reading)
    except Exception as err:
        logger.exception("Could not store reading")
        return jsonify({'success': False, 'error': str(err)}), 500

    logger.info("Recorded reading: %s", ", ".join(f"{k}={v}" for k, v in reading.items()))
    _prune_if_due()
    return jsonify({
        'success': True,
        'recorded_at': datetime.fromtimestamp(recorded_at).isoformat(),
        'fields': sorted(reading),
    })


def _serve_reading(row):
    """Shape a stored row for the apps, with an honest freshness signal."""
    recorded_at = row.pop('recorded_at')
    age = max(0.0, time.time() - recorded_at)
    payload = {k: v for k, v in row.items() if v is not None}
    payload['recorded_at'] = datetime.fromtimestamp(recorded_at).isoformat()
    payload['age_seconds'] = round(age, 1)
    # The displays need to be able to tell "this is now" from "this is whatever
    # the sensor last managed to send", rather than rendering both identically.
    payload['stale'] = age > config.WEATHER_STALE_AFTER
    return payload


@app.route('/api/weather', methods=['GET'])
@require_token(lambda: config.READ_TOKEN)
def api_weather():
    """The latest reading — what the TV and phone apps poll."""
    try:
        row = weather_store.latest(config.WEATHER_DB_PATH)
    except Exception as err:
        logger.exception("Could not read the weather store")
        return jsonify({'success': False, 'error': str(err)}), 500

    if row is None:
        return jsonify({
            'success': False,
            'error': 'no readings yet',
            'hint': 'The weather station has not posted to /ingest.',
        }), 404

    return jsonify(_serve_reading(dict(row)))


@app.route('/api/weather/history', methods=['GET'])
@require_token(lambda: config.READ_TOKEN)
def api_weather_history():
    """Recent readings — this is what replaces the SmartThings history."""
    try:
        hours = float(request.args.get('hours', 24))
    except ValueError:
        return jsonify({'success': False, 'error': 'hours must be a number'}), 400
    hours = max(0.1, min(hours, 24 * 31))

    try:
        rows = weather_store.history(config.WEATHER_DB_PATH, hours=hours)
    except Exception as err:
        logger.exception("Could not read history")
        return jsonify({'success': False, 'error': str(err)}), 500

    return jsonify({
        'hours': hours,
        'count': len(rows),
        'readings': [
            {**{k: v for k, v in r.items() if k != 'recorded_at' and v is not None},
             'recorded_at': datetime.fromtimestamp(r['recorded_at']).isoformat()}
            for r in rows
        ],
    })


@app.route('/device-status', methods=['GET'])
def device_status():
    """Get TV device status"""
    try:
        target = request.args.get('target', 's95')
        if target == 'm7':
            device_id = config.TV_DEVICE_ID_M7
            device_name = "M7 Monitor"
        else:
            device_id = config.TV_DEVICE_ID_S95
            device_name = "S95 TV"
        
        if not device_id:
            return jsonify({
                'success': False,
                'error': f'Device ID not configured for {device_name}'
            }), 500
        
        status = st_api.get_device_status(device_id)
        
        if status:
            return jsonify({
                'success': True,
                'device': device_name,
                'status': status
            })
        
        return jsonify({
            'success': False,
            'error': 'Failed to get device status'
        }), 500
    except Exception as e:
        logger.exception("Unexpected error while getting device status")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/config', methods=['GET'])
def get_config():
    """Get current configuration (for debugging)"""
    return jsonify({
        'launch_method': 'local REST (no SmartThings)',
        's95_tv_host': config.TV_HOST_S95 or 'Not set',
        'm7_monitor_host': config.TV_HOST_M7 or 'Not set',
        'tv_app_id': config.TV_APP_ID or 'Not set',
        'ready_timeout_seconds': config.TV_READY_TIMEOUT,
        'launch_attempts': config.TV_LAUNCH_ATTEMPTS,
        'auth': {
            'ingest': 'token required' if config.INGEST_TOKEN else 'OPEN - set INGEST_TOKEN',
            'read': 'token required' if config.READ_TOKEN else 'OPEN - set READ_TOKEN',
            'launch': 'token required' if config.ACTION_TOKEN else 'open (Edge driver sends none)',
        },
        'weather_db': config.WEATHER_DB_PATH,
        'retention_days': config.WEATHER_RETENTION_DAYS,
    })

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("TV App Launcher Utility Starting")
    logger.info("=" * 60)
    logger.info(f"Host: {config.HOST}")
    logger.info(f"Port: {config.PORT}")
    logger.info(f"S95 TV host: {config.TV_HOST_S95 or 'NOT SET'}")
    logger.info(f"M7 Monitor host: {config.TV_HOST_M7 or 'NOT SET'}")
    logger.info(f"TV App ID: {config.TV_APP_ID or 'NOT SET'}")
    logger.info("Launch method: local REST on port %d (no SmartThings)", tv_local.TV_REST_PORT)
    logger.info("=" * 60)
    
    app.run(host=config.HOST, port=config.PORT, debug=False)

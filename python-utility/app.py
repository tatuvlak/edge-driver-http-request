"""
TV App Launcher Utility
Receives HTTP requests from SmartThings Edge Driver and launches TV app via SmartThings API
"""

from flask import Flask, request, jsonify, redirect, session
import requests
import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

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
    
    # OAuth server configuration (for initial authorization flow)
    OAUTH_REDIRECT_URI = os.environ.get('OAUTH_REDIRECT_URI', 'http://localhost:5000/oauth/callback')
    
    # TV/Monitor configuration
    # S95 TV (default)
    TV_DEVICE_ID_S95 = os.environ.get('TV_DEVICE_ID_S95', os.environ.get('TV_DEVICE_ID', ''))
    # M7 Monitor
    TV_DEVICE_ID_M7 = os.environ.get('TV_DEVICE_ID_M7', '')
    
    TV_APP_ID = os.environ.get('TV_APP_ID', '')  # Your weather app ID
    
    # Server configuration
    PORT = int(os.environ.get('PORT', 5000))
    HOST = os.environ.get('HOST', '0.0.0.0')
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

config = Config()

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
                    logger.info("OAuth tokens loaded from file")
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
            
            data = {
                'access_token': self.access_token,
                'refresh_token': self.refresh_token,
                'expires_at': self.token_expires_at,
                'updated_at': datetime.now().isoformat()
            }
            
            with open(token_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("OAuth tokens saved to file")
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
            
            # Update refresh token if a new one is provided
            new_refresh_token = token_data.get('refresh_token')
            if new_refresh_token:
                self.refresh_token = new_refresh_token
                logger.info("Refresh token updated")
            
            # Save tokens to file
            self._save_tokens()
            
            logger.info(f"OAuth token refreshed successfully (expires in {expires_in}s)")
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
    logger.warning("Neither OAuth nor PAT configured! Authentication will fail.")
elif use_oauth:
    logger.info("Using OAuth authentication")
else:
    logger.info("Using PAT authentication (OAuth not configured)")
    
st_api = SmartThingsAPI(use_oauth=use_oauth)

# Set Flask secret key for sessions
app.secret_key = config.SECRET_KEY

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '2.0.0',
        'auth_method': 'OAuth' if st_api.use_oauth else 'PAT'
    })

@app.route('/oauth/authorize', methods=['GET'])
def oauth_authorize():
    """Start OAuth authorization flow"""
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
    query = '&'.join([f"{k}={v}" for k, v in params.items()])
    full_url = f"{auth_url}?{query}"
    
    logger.info(f"Redirecting to OAuth authorization URL")
    return redirect(full_url)

@app.route('/oauth/callback', methods=['GET'])
def oauth_callback():
    """OAuth callback endpoint"""
    code = request.args.get('code')
    error = request.args.get('error')
    
    if error:
        logger.error(f"OAuth error: {error}")
        return jsonify({
            'success': False,
            'error': error
        }), 400
    
    if not code:
        return jsonify({
            'success': False,
            'error': 'No authorization code received'
        }), 400
    
    # Exchange code for tokens
    token_url = "https://api.smartthings.com/oauth/token"
    data = {
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
        data['client_id'] = config.ST_CLIENT_ID
    
    try:
        response = requests.post(
            token_url,
            data=data,
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
        
        token_data = response.json()
        
        # Update API client with new tokens
        st_api.access_token = token_data.get('access_token')
        st_api.refresh_token = token_data.get('refresh_token')
        
        expires_in = token_data.get('expires_in', 86400)
        st_api.token_expires_at = datetime.now().timestamp() + expires_in
        
        # Save tokens
        st_api._save_tokens()
        
        logger.info("OAuth authorization successful!")
        
        return jsonify({
            'success': True,
            'message': 'OAuth authorization successful! Tokens saved.',
            'expires_in': expires_in
        })
        
    except Exception as e:
        logger.exception("Failed to exchange authorization code for tokens")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/launch-tv-app', methods=['POST'])
def launch_tv_app():
    """Launch TV app endpoint - called by Edge Driver"""
    try:
        data = request.get_json(silent=True) or {}
        # Determine which device to use based on target_device parameter
        target_device = data.get('target_device') or data.get('target') or 's95'  # Default to S95 TV
        
        if target_device == 'm7':
            device_id = config.TV_DEVICE_ID_M7
            device_name = "M7 Monitor"
        else:
            device_id = config.TV_DEVICE_ID_S95
            device_name = "S95 TV"
        
        logger.info(f"Target device: {device_name} ({target_device})")
        
        # Validate configuration
        if not device_id:
            return jsonify({
                'success': False,
                'error': f'Device ID not configured for {device_name}'
            }), 500
        
        if not config.TV_APP_ID:
            return jsonify({
                'success': False,
                'error': 'TV_APP_ID not configured'
            }), 500
        
        # Authentication check is now handled in get_headers()
        # which will automatically refresh token if needed
        
        # Launch the app
        success, result = st_api.launch_app(device_id, config.TV_APP_ID)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'TV app launched successfully on {device_name}',
                'device': device_name,
                'timestamp': datetime.now().isoformat(),
                'result': result
            })
        
        return jsonify({
            'success': False,
            'error': result
        }), 500
    except Exception as e:
        logger.exception("Unexpected error while launching TV app")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

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
    logger.info(f"Config check - S95 TV device ID: {config.TV_DEVICE_ID_S95}")
    logger.info(f"Config check - M7 Monitor device ID: {config.TV_DEVICE_ID_M7}")
    logger.info(f"Config check - TV_APP_ID from config object: {config.TV_APP_ID}")
    logger.info(f"Config check - ST_PAT from config object: {config.ST_PAT[:8] if config.ST_PAT else 'Not set'}...")
    
    return jsonify({
        's95_tv_device_id': config.TV_DEVICE_ID_S95[:8] + '...' if config.TV_DEVICE_ID_S95 else 'Not set',
        'm7_monitor_device_id': config.TV_DEVICE_ID_M7[:8] + '...' if config.TV_DEVICE_ID_M7 else 'Not set',
        'tv_app_id': config.TV_APP_ID if config.TV_APP_ID else 'Not set',
        'auth_method': 'OAuth' if st_api.use_oauth else 'PAT',
        'auth_configured': bool(st_api.use_oauth and st_api.refresh_token) or bool(config.ST_PAT),
        'oauth_token_valid': st_api.access_token and not st_api.is_token_expired() if st_api.use_oauth else None,
        'token_expires_at': datetime.fromtimestamp(st_api.token_expires_at).isoformat() if st_api.token_expires_at else None
    })

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("TV App Launcher Utility Starting")
    logger.info("=" * 60)
    logger.info(f"Host: {config.HOST}")
    logger.info(f"Port: {config.PORT}")
    logger.info(f"S95 TV Device ID: {config.TV_DEVICE_ID_S95[:8] + '...' if config.TV_DEVICE_ID_S95 else 'NOT SET'}")
    logger.info(f"M7 Monitor Device ID: {config.TV_DEVICE_ID_M7[:8] + '...' if config.TV_DEVICE_ID_M7 else 'NOT SET'}")
    logger.info(f"TV App ID: {config.TV_APP_ID if config.TV_APP_ID else 'NOT SET'}")
    logger.info(f"Auth Method: {'OAuth' if st_api.use_oauth else 'PAT'}")
    logger.info(f"Auth Configured: {bool(config.ST_PAT or st_api.access_token)}")
    logger.info("=" * 60)
    
    app.run(host=config.HOST, port=config.PORT, debug=False)

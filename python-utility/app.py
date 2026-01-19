"""
TV App Launcher Utility
Receives HTTP requests from SmartThings Edge Driver and launches TV app via SmartThings API
"""

from flask import Flask, request, jsonify
import requests
import os
import logging
from datetime import datetime
from dotenv import load_dotenv

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
    ST_PAT = os.environ.get('SMARTTHINGS_PAT', '')  # Personal Access Token
    
    # OAuth configuration (for future use)
    ST_CLIENT_ID = os.environ.get('ST_CLIENT_ID', '')
    ST_CLIENT_SECRET = os.environ.get('ST_CLIENT_SECRET', '')
    ST_REFRESH_TOKEN = os.environ.get('ST_REFRESH_TOKEN', '')
    
    # TV/Monitor configuration
    # S95 TV (default)
    TV_DEVICE_ID_S95 = os.environ.get('TV_DEVICE_ID_S95', os.environ.get('TV_DEVICE_ID', ''))
    # M7 Monitor
    TV_DEVICE_ID_M7 = os.environ.get('TV_DEVICE_ID_M7', '')
    
    TV_APP_ID = os.environ.get('TV_APP_ID', '')  # Your weather app ID
    
    # Server configuration
    PORT = int(os.environ.get('PORT', 5000))
    HOST = os.environ.get('HOST', '0.0.0.0')

config = Config()

class SmartThingsAPI:
    """SmartThings API client"""
    
    def __init__(self, use_oauth=False):
        self.use_oauth = use_oauth
        self.access_token = None
        self.token_expires_at = None
        
    def get_headers(self):
        """Get API request headers"""
        if self.use_oauth and self.access_token:
            token = self.access_token
        else:
            token = config.ST_PAT
            
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
        if not config.ST_CLIENT_ID or not config.ST_REFRESH_TOKEN:
            logger.error("OAuth credentials not configured")
            return False
            
        # SmartThings uses /oauth/token endpoint
        token_url = "https://api.smartthings.com/oauth/token"
        
        # Prepare form data
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': config.ST_REFRESH_TOKEN
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
                config.ST_REFRESH_TOKEN = new_refresh_token
                logger.info("Refresh token updated (you may want to persist this)")
            
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
# Set use_oauth=True when OAuth is configured
st_api = SmartThingsAPI(use_oauth=False)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })

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
        
        if not config.ST_PAT and not st_api.access_token:
            return jsonify({
                'success': False,
                'error': 'SmartThings authentication not configured'
            }), 500
        
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
        'auth_configured': bool(config.ST_PAT or st_api.access_token)
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

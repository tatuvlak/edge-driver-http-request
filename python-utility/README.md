# TV App Launcher - Python Utility

A Flask-based HTTP service that receives requests from SmartThings Edge Driver and launches apps on Samsung TVs using the SmartThings API.

## Version 2.0 - OAuth Support

**New in v2.0:**
- ✅ OAuth 2.0 authentication (recommended)
- ✅ Automatic token refresh
- ✅ Persistent token storage
- ✅ OAuth authorization flow endpoints
- ⚠️ PAT authentication (deprecated, fallback only)

## Quick Links

- **[OAuth Setup Guide](./OAUTH_SETUP.md)** - Start here for new installations
- **[Migration Guide](./OAUTH_MIGRATION.md)** - Upgrading from v1.x (PAT) to v2.0 (OAuth)

## Features

- **HTTP API** for launching TV apps remotely
- **Multi-device support** (S95 TV and M7 Monitor)
- **OAuth 2.0** with automatic token refresh
- **Health monitoring** endpoint
- **Docker support** with persistent storage
- **Automatic retry** on token expiration

## Authentication Methods

### OAuth 2.0 (Recommended) ✅
- Automatic token refresh
- Better security
- No manual token rotation needed
- Supports long-running deployments

### Personal Access Token (Deprecated) ⚠️
- Requires manual token management
- Limited lifetime
- Will be removed in future versions

## Quick Start

### 1. Prerequisites
- Docker and Docker Compose
- SmartThings Developer account
- SmartThings devices (Samsung TV/Monitor)
- **Note**: Service runs on local NAS - uses external OAuth callback (GitHub Pages)

### 2. Setup OAuth

Follow the [OAuth Setup Guide](./OAUTH_SETUP.md) for detailed instructions.

**Quick version:**
1. Register OAuth app at https://smartthings.developer.samsung.com/
   - Set redirect URI to: `https://tatuvlak.github.io/tv-weather-oauth/callback.html`
2. Configure `.env` with your credentials
3. Run `docker-compose up --build -d`
4. Get authorization URL: `curl http://your-nas:5000/oauth/authorize`
5. Open URL in browser, authorize, and copy the code from callback page
6. Submit code: `curl -X POST http://your-nas:5000/oauth/token -H "Content-Type: application/json" -d '{"code":"your-code"}'`
7. Done! Tokens are auto-managed

### 3. Configuration

Create `.env` file (see [.env.example](./.env.example)):

```env
# OAuth Configuration
ST_CLIENT_ID=your-client-id
ST_CLIENT_SECRET=your-client-secret
# External callback (GitHub Pages) - required for local NAS deployment
OAUTH_REDIRECT_URI=https://tatuvlak.github.io/tv-weather-oauth/callback.html
SECRET_KEY=your-random-secret-key

# Device Configuration
TV_DEVICE_ID_S95=your-s95-device-id
TV_APP_ID=your-tizen-app-id
```

### 4. Deploy

```bash
docker-compose up --build -d
```

### 5. Authorize (first time only)

Open in browser: `http://your-server:5000/oauth/authorize`

## API Endpoints

### POST `/launch-tv-app`
Launch the TV app on specified device.

**Request:**
```json
{
  "target_device": "s95"  // or "m7"
}
```

**Response:**
```json
{
  "success": true,
  "message": "TV app launched successfully on S95 TV",
  "device": "S95 TV",
  "timestamp": "2026-01-19T..."
}
```

### GET `/config`
View current configuration and auth status.

**Response:**
```json
{
  "auth_method": "OAuth",
  "auth_configured": true,
  "oauth_token_valid": true,
  "token_expires_at": "2026-01-20T..."
}
```

### GET `/health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "auth_method": "OAuth",
  "timestamp": "2026-01-19T..."
}
```

### GET `/oauth/authorize`
Get the OAuth authorization URL for manual authorization flow.

**Usage (for local NAS deployment):**
```bash
curl http://your-nas:5000/oauth/authorize
```

**Response:**
```json
{
  "success": true,
  "authorization_url": "https://api.smartthings.com/oauth/authorize?...",
  "instructions": [
    "1. Open the authorization_url in your browser",
    "2. Log in with your SmartThings account and authorize",
    "3. You will be redirected to the callback page with the code",
    "4. Copy the authorization code from the callback page",
    "5. POST the code to /oauth/token endpoint"
  ],
  "callback_url": "https://tatuvlak.github.io/tv-weather-oauth/callback.html",
  "token_endpoint": "/oauth/token"
}
```

### POST `/oauth/token`
Exchange authorization code for access/refresh tokens (manual flow).

**Request:**
```bash
curl -X POST http://your-nas:5000/oauth/token \
  -H "Content-Type: application/json" \
  -d '{"code": "authorization-code-from-callback"}'
```

**Response:**
```json
{
  "success": true,
  "message": "OAuth authorization successful! Tokens saved.",
  "expires_in": 86400,
  "expires_at": "2026-01-20T15:30:00"
}
```

### GET `/device-status?target=s95`
Get device status from SmartThings API.

## Environment Variables

### OAuth Configuration
| Variable | Required | Description |
|----------|----------|-------------|
| `ST_CLIENT_ID` | Yes | SmartThings OAuth client ID |
| `ST_CLIENT_SECRET` | Recommended | OAuth client secret |
| `ST_REFRESH_TOKEN` | Optional* | Initial refresh token |
| `OAUTH_REDIRECT_URI` | Yes | External callback URL (default: GitHub Pages) |
| `TOKEN_FILE` | No | Token storage path (default: `/app/data/oauth_tokens.json`) |
| `SECRET_KEY` | Yes | Flask session secret |

*Can be obtained through manual authorization flow

### Device Configuration
| Variable | Required | Description |
|----------|----------|-------------|
| `TV_DEVICE_ID_S95` | Yes | S95 TV device ID |
| `TV_DEVICE_ID_M7` | No | M7 Monitor device ID |
| `TV_APP_ID` | Yes | Tizen app ID to launch |

### Legacy Configuration
| Variable | Required | Description |
|----------|----------|-------------|
| `SMARTTHINGS_PAT` | No | Personal Access Token (deprecated) |

## Token Management

### Automatic Features
- ✅ Tokens refresh automatically before expiration (5-min buffer)
- ✅ Tokens persist across container restarts
- ✅ Failed API calls trigger token refresh
- ✅ Startup validation and refresh if needed

### Manual Operations
```bash
# View token status
curl http://your-nas:5000/config

# Get authorization URL for new authorization
curl http://your-nas:5000/oauth/authorize

# Exchange code for tokens (after authorizing in browser)
curl -X POST http://your-nas:5000/oauth/token \
  -H "Content-Type: application/json" \
  -d '{"code": "your-authorization-code"}'

# View token file
docker exec tv-app-launcher cat /app/data/oauth_tokens.json

# Check logs for refresh activity
docker logs tv-app-launcher | grep -i token
```

## Docker Deployment

### Build and Run
```bash
docker-compose up --build -d
```

### View Logs
```bash
docker logs -f tv-app-launcher
```

### Restart
```bash
docker-compose restart
```

### Stop
```bash
docker-compose down
```

## Volume Mounts

The container uses a volume to persist OAuth tokens:
```yaml
volumes:
  - /share/Container/tv-app-launcher/data:/app/data
```

Ensure this directory exists and is writable:
```bash
mkdir -p /share/Container/tv-app-launcher/data
chmod 755 /share/Container/tv-app-launcher/data
```

## Troubleshooting

### "No authentication token available"
1. Check OAuth credentials in `.env`
2. Get authorization URL: `curl http://your-nas:5000/oauth/authorize`
3. Open the URL in browser, authorize, and copy the code
4. Submit code: `curl -X POST http://your-nas:5000/oauth/token -H "Content-Type: application/json" -d '{"code":"your-code"}'`
5. Check token file exists: `docker exec tv-app-launcher ls -la /app/data/`

### "Token refresh failed"
1. Check logs: `docker logs tv-app-launcher`
2. Verify `ST_CLIENT_ID` and `ST_CLIENT_SECRET` are correct
3. Re-run authorization flow to get fresh tokens

### Tokens not persisting
1. Check volume mount: `docker inspect tv-app-launcher | grep -A 5 Mounts`
2. Verify directory exists: `ls -la /share/Container/tv-app-launcher/data/`
3. Check permissions: `chmod 755 /share/Container/tv-app-launcher/data`

### Redirect URI mismatch
1. Verify redirect URI in SmartThings Developer Workspace
2. Must be: `https://tatuvlak.github.io/tv-weather-oauth/callback.html`
3. Check `.env` has correct `OAUTH_REDIRECT_URI`

## Development

### Local Testing
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export ST_CLIENT_ID=your-client-id
export ST_CLIENT_SECRET=your-client-secret
# ... other variables

# Run application
python app.py
```

### Running Tests
```bash
# Health check
curl http://localhost:5000/health

# Config check
curl http://localhost:5000/config

# Launch test
curl -X POST http://localhost:5000/launch-tv-app \
  -H "Content-Type: application/json" \
  -d '{"target_device": "s95"}'
```

## Security

- Store sensitive values in `.env` (not committed to git)
- Use strong `SECRET_KEY` for production
- Secure your token file (600 or 640 permissions)
- Use HTTPS in production
- Rotate `ST_CLIENT_SECRET` periodically
- Monitor logs for authentication failures

## Migration from v1.x

See [OAUTH_MIGRATION.md](./OAUTH_MIGRATION.md) for complete migration guide from PAT to OAuth.

**Quick migration:**
1. Get OAuth credentials from SmartThings Developer Workspace
2. Update `.env` with OAuth settings
3. Run authorization flow
4. Remove `SMARTTHINGS_PAT` from `.env`

## Integration with Edge Driver

This utility is designed to work with SmartThings Edge Drivers. The Edge Driver sends HTTP requests to this service to launch TV apps.

**Edge Driver → Python Utility → SmartThings API → TV**

Example Edge Driver call:
```lua
local http = require "socket.http"
local ltn12 = require "ltn12"
local json = require "dkjson"

local function launch_app(target_device)
  local url = "http://your-server:5000/launch-tv-app"
  local body = json.encode({target_device = target_device})
  
  local response_body = {}
  local res, code = http.request({
    url = url,
    method = "POST",
    headers = {
      ["Content-Type"] = "application/json",
      ["Content-Length"] = #body
    },
    source = ltn12.source.string(body),
    sink = ltn12.sink.table(response_body)
  })
  
  return code == 200
end
```

## Support

- **Issues**: Check logs with `docker logs tv-app-launcher`
- **Configuration**: Review `/config` endpoint
- **Documentation**: See `OAUTH_SETUP.md` and `OAUTH_MIGRATION.md`
- **SmartThings API**: https://developer-preview.smartthings.com/docs/

## License

[Your License Here]

## Version History

- **v2.0.0** - OAuth 2.0 support, automatic token refresh, persistent storage
- **v1.0.0** - Initial release with PAT authentication

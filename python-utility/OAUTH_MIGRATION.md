# OAuth Migration Guide

## Overview

This version of the python-utility has been updated to use **OAuth authentication** instead of Personal Access Tokens (PAT). OAuth provides better security and allows for automatic token refresh.

## What Changed

### Version 1.x (PAT-based)
- Used `SMARTTHINGS_PAT` environment variable
- Required manual token rotation
- No automatic token refresh

### Version 2.0 (OAuth-based)
- Uses OAuth 2.0 flow with refresh tokens
- Automatic token refresh before expiration
- Persistent token storage across restarts
- Falls back to PAT if OAuth is not configured
- New endpoints for OAuth authorization

## Migration Steps

### Option 1: Using Existing Refresh Token (Recommended)

If you already have a SmartThings OAuth refresh token:

1. **Set environment variables** in your `.env` file:
   ```env
   # Required for OAuth
   ST_CLIENT_ID=your-client-id
   ST_CLIENT_SECRET=your-client-secret  # Optional but recommended
   ST_REFRESH_TOKEN=your-refresh-token
   
   # Optional - customize token storage location
   TOKEN_FILE=/app/data/oauth_tokens.json
   OAUTH_REDIRECT_URI=http://your-server:5000/oauth/callback
   SECRET_KEY=your-secret-key-for-flask-sessions
   
   # Your existing device configuration
   TV_DEVICE_ID_S95=your-tv-device-id
   TV_APP_ID=your-app-id
   ```

2. **Deploy the updated container**:
   ```bash
   docker-compose down
   docker-compose up --build -d
   ```

3. **Verify authentication**:
   ```bash
   curl http://localhost:5000/config
   ```

   You should see:
   ```json
   {
     "auth_method": "OAuth",
     "auth_configured": true,
     "oauth_token_valid": true
   }
   ```

### Option 2: New OAuth Authorization Flow

If you need to obtain a new OAuth refresh token:

1. **Configure SmartThings Developer Workspace**:
   - Go to https://smartthings.developer.samsung.com/
   - Register your application
   - Add OAuth redirect URI: `http://your-server:5000/oauth/callback`
   - Note your Client ID and Client Secret

2. **Set minimum environment variables**:
   ```env
   ST_CLIENT_ID=your-client-id
   ST_CLIENT_SECRET=your-client-secret
   OAUTH_REDIRECT_URI=http://your-server:5000/oauth/callback
   SECRET_KEY=your-secret-key
   ```

3. **Start the container**:
   ```bash
   docker-compose up --build -d
   ```

4. **Initiate OAuth flow**:
   - Visit: `http://your-server:5000/oauth/authorize`
   - Log in with your SmartThings account
   - Grant permissions
   - You'll be redirected back with success message

5. **Verify tokens are saved**:
   ```bash
   # Check the token file exists
   docker exec tv-app-launcher ls -la /app/data/
   
   # Verify configuration
   curl http://localhost:5000/config
   ```

### Option 3: Continue Using PAT (Not Recommended)

If you want to continue using PAT temporarily:

1. **Keep your existing configuration**:
   ```env
   SMARTTHINGS_PAT=your-pat-token
   ```

2. **The application will automatically use PAT** if OAuth is not configured

3. **Plan migration to OAuth** - PAT support may be removed in future versions

## New Endpoints

### `/oauth/authorize` (GET)
Initiates the OAuth authorization flow. Redirects to SmartThings login.

**Usage:**
```bash
# Open in browser
http://your-server:5000/oauth/authorize
```

### `/oauth/callback` (GET)
OAuth callback endpoint. Handles the authorization response and saves tokens.

**This endpoint is called automatically** by SmartThings after user authorization.

### `/config` (GET) - Enhanced
Now shows OAuth status and token expiration.

**Response:**
```json
{
  "auth_method": "OAuth",
  "auth_configured": true,
  "oauth_token_valid": true,
  "token_expires_at": "2026-01-20T15:30:00"
}
```

## Token Management

### Token Storage
- Tokens are stored in `/app/data/oauth_tokens.json`
- The file persists across container restarts via Docker volume
- Contains: `access_token`, `refresh_token`, `expires_at`, `updated_at`

### Automatic Token Refresh
- Access tokens are automatically refreshed before expiration
- Refresh happens on startup if token is expired
- Refresh happens before API calls if token will expire soon (5-minute buffer)
- New refresh tokens are automatically saved if provided

### Manual Token Refresh
If you need to manually check/refresh tokens:

```bash
# View current token status
curl http://localhost:5000/config

# Make any API call - token will auto-refresh if needed
curl -X POST http://localhost:5000/launch-tv-app \
  -H "Content-Type: application/json" \
  -d '{"target_device": "s95"}'
```

## Troubleshooting

### "No authentication token available"
- **Check**: OAuth credentials are set in environment variables
- **Check**: Token file exists and is readable
- **Solution**: Run OAuth authorization flow or set ST_REFRESH_TOKEN

### "Token refresh failed: 401"
- **Cause**: Refresh token is invalid or expired
- **Solution**: Re-run OAuth authorization flow to get new tokens

### "OAuth client ID not configured"
- **Cause**: ST_CLIENT_ID environment variable is missing
- **Solution**: Add ST_CLIENT_ID to your .env file

### Token file not persisting
- **Check**: Docker volume is properly mounted
- **Check**: Directory permissions (should be writable)
- **Solution**: Verify docker-compose.yml has volume mapping:
  ```yaml
  volumes:
    - /share/Container/tv-app-launcher/data:/app/data
  ```

## Security Considerations

1. **Token File Security**
   - The `oauth_tokens.json` file contains sensitive credentials
   - Ensure proper file permissions (600 or 640)
   - Don't commit this file to version control

2. **Environment Variables**
   - Store sensitive values in `.env` file
   - Don't commit `.env` to version control
   - Use Docker secrets in production environments

3. **Client Secret**
   - Keep your ST_CLIENT_SECRET confidential
   - Use environment variables, never hardcode
   - Rotate periodically

4. **Flask Secret Key**
   - Set a strong SECRET_KEY for production
   - Required for session management
   - Change from default value

## Required Scopes

The application requires these SmartThings OAuth scopes:
- `r:devices:*` - Read device information
- `x:devices:*` - Execute device commands

Add these when configuring your OAuth application in SmartThings Developer Workspace.

## Rollback

If you need to rollback to PAT-based authentication:

1. Ensure `SMARTTHINGS_PAT` is set in your environment
2. Remove or unset OAuth variables (`ST_CLIENT_ID`, `ST_REFRESH_TOKEN`)
3. Restart the container

The application will automatically detect and use PAT when OAuth is not configured.

## Support

For issues or questions:
- Check logs: `docker logs tv-app-launcher`
- Verify configuration: `curl http://localhost:5000/config`
- Review environment variables: `docker exec tv-app-launcher env | grep ST_`

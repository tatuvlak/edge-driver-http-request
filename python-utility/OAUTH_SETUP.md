# Quick Start: OAuth Setup (Local NAS Deployment)

This guide will help you set up OAuth authentication for the TV App Launcher utility running on a local NAS.

**Important**: Since this service runs on a local NAS (not accessible from the internet), we use an external OAuth callback page hosted on GitHub Pages (from the tv-weather-oauth project).

## Prerequisites

- Docker and Docker Compose installed on your NAS
- SmartThings Developer account
- Access to your SmartThings devices
- GitHub Pages callback URL (already set up at: https://tatuvlak.github.io/tv-weather-oauth/callback.html)

## Step 1: Register OAuth Application

1. Go to [SmartThings Developer Workspace](https://smartthings.developer.samsung.com/)
2. Sign in with your SmartThings account
3. Navigate to **Workspace** → **OAuth Clients** → **Create New OAuth Client**
4. Fill in the details:
   - **Name**: TV App Launcher
   - **Redirect URI**: `https://tatuvlak.github.io/tv-weather-oauth/callback.html`
     - ⚠️ **Important**: Use the external GitHub Pages URL, NOT your local NAS URL
     - This is the same callback used for your Samsung TV Weather app
   - **Scopes**: 
     - `r:devices:*` (Read devices)
     - `x:devices:*` (Execute device commands)
5. **Save** and note your:
   - Client ID
   - Client Secret

## Step 2: Configure Environment Variables

Create or update `/share/Container/tv-app-launcher/.env`:

```env
# SmartThings OAuth
ST_CLIENT_ID=your-client-id-from-step-1
ST_CLIENT_SECRET=your-client-secret-from-step-1

# OAuth Callback (External GitHub Pages - DO NOT CHANGE unless you host your own)
OAUTH_REDIRECT_URI=https://tatuvlak.github.io/tv-weather-oauth/callback.html
TOKEN_FILE=/app/data/oauth_tokens.json
SECRET_KEY=generate-random-string-here

# Device Configuration (keep your existing values)
TV_DEVICE_ID_S95=your-s95-tv-device-id
TV_DEVICE_ID_M7=your-m7-monitor-device-id
TV_APP_ID=your-weather-app-id
```

**Note**: Don't set `ST_REFRESH_TOKEN` yet - we'll get it in the authorization flow.

## Step 3: Deploy the Container

```bash
# Navigate to the python-utility directory
cd /share/Container/tv-app-launcher

# Stop existing container if running
docker-compose down

# Build and start new container
docker-compose up --build -d

# Check logs
docker logs -f tv-app-launcher
```

## Step 4: Obtain OAuth Tokens (Manual Flow)

Since your NAS is not accessible from the internet, we use a **manual OAuth flow** with an external callback page.

### Authorization Process

1. **Get the authorization URL** from your NAS:
   ```bash
   curl http://your-nas-ip:5000/oauth/authorize
   ```
   
   This will return a JSON response:
   ```json
   {
     "success": true,
     "authorization_url": "https://api.smartthings.com/oauth/authorize?...",
     "instructions": [
       "1. Open the authorization_url in your browser",
       "2. Log in with your SmartThings account and authorize",
       "3. You will be redirected to the callback page with the code",
       "4. Copy the authorization code from the callback page",
       "5. POST the code to /oauth/token endpoint: {\"code\": \"your-code\"}"
     ],
     "callback_url": "https://tatuvlak.github.io/tv-weather-oauth/callback.html",
     "token_endpoint": "/oauth/token"
   }
   ```

2. **Open the authorization URL** in your browser (copy the `authorization_url` from above)

3. **Log in** with your SmartThings account and **grant permissions**

4. **You'll be redirected** to the GitHub Pages callback:
   - URL: `https://tatuvlak.github.io/tv-weather-oauth/callback.html?code=...`
   - The page will display your authorization code in a large box
   - Click "Copy Code" to copy it to your clipboard

5. **Submit the code** to your NAS service:
   ```bash
   curl -X POST http://your-nas-ip:5000/oauth/token \
     -H "Content-Type: application/json" \
     -d '{"code": "paste-your-code-here"}'
   ```
   
   Expected response:
   ```json
   {
     "success": true,
     "message": "OAuth authorization successful! Tokens saved.",
     "expires_in": 86400,
     "expires_at": "2026-01-20T..."
   }
   ```

6. **Verify tokens are saved**:
   ```bash
   # Check token file exists
   docker exec tv-app-launcher cat /app/data/oauth_tokens.json
   
   # Verify configuration
   curl http://your-nas-ip:5000/config
   ```

### Alternative: Use Existing Refresh Token

If you already have a refresh token from a previous setup:

1. **Add to .env file**:
   ```env
   ST_REFRESH_TOKEN=your-existing-refresh-token
   ```

2. **Restart container**:
   ```bash
   docker-compose restart
   ```

3. **Verify**:
   ```bash
   curl http://your-nas-ip:5000/config
   ```

## Step 5: Test the Setup

### Test 1: Check Configuration
```bash
curl http://your-server-ip:5000/config
```

Expected response:
```json
{
  "auth_method": "OAuth",
  "auth_configured": true,
  "oauth_token_valid": true,
  "token_expires_at": "2026-01-20T..."
}
```

### Test 2: Launch TV App
```bash
curl -X POST http://your-server-ip:5000/launch-tv-app \
  -H "Content-Type: application/json" \
  -d '{"target_device": "s95"}'
```

Expected response:
```json
{
  "success": true,
  "message": "TV app launched successfully on S95 TV",
  "device": "S95 TV"
}
```

### Test 3: Health Check
```bash
curl http://your-server-ip:5000/health
```

Expected response:
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "auth_method": "OAuth"
}
```

## Troubleshooting

### Issue: "OAuth client ID not configured"
**Solution**: Make sure `ST_CLIENT_ID` is set in your `.env` file and restart the container.

### Issue: "No authentication token available"
**Solution**: 
1. Check if token file exists: `docker exec tv-app-launcher ls -la /app/data/`
2. If missing, run OAuth authorization flow (Step 4)

### Issue: Redirect URI mismatch
**Error**: `redirect_uri_mismatch` in OAuth callback page

**Solution**: 
1. Check your OAuth client settings in SmartThings Developer Workspace
2. Ensure the redirect URI is exactly: `https://tatuvlak.github.io/tv-weather-oauth/callback.html`
3. Make sure `.env` has: `OAUTH_REDIRECT_URI=https://tatuvlak.github.io/tv-weather-oauth/callback.html`
4. Restart container

### Issue: 401 Unauthorized
**Cause**: Token expired or invalid

**Solution**: 
1. Check logs: `docker logs tv-app-launcher`
2. The app should auto-refresh - if not, re-run OAuth flow
3. If refresh token is invalid, start from Step 4 again

### Issue: Tokens not persisting
**Solution**:
1. Verify volume mount: `docker inspect tv-app-launcher | grep -A 5 Mounts`
2. Check directory permissions: `ls -la /share/Container/tv-app-launcher/data/`
3. Ensure directory exists: `mkdir -p /share/Container/tv-app-launcher/data`

## Token Lifecycle

- **Access Token**: Valid for 24 hours (86400 seconds)
- **Automatic Refresh**: Happens 5 minutes before expiration
- **Refresh Token**: Long-lived, used to obtain new access tokens
- **Storage**: Persisted in `/app/data/oauth_tokens.json`

The application automatically handles token refresh - you don't need to do anything!

## Next Steps

1. ✅ OAuth is now configured
2. ✅ Tokens are automatically refreshed
3. 📝 Consider setting up monitoring for token refresh failures
4. 📝 Backup your `.env` file securely
5. 📝 Consider rotating your `SECRET_KEY` periodically

## Security Best Practices

1. **Never commit** `.env` or `oauth_tokens.json` to version control
2. **Secure your token storage** - ensure proper file permissions
3. **Use HTTPS** in production environments
4. **Rotate secrets** periodically (CLIENT_SECRET, SECRET_KEY)
5. **Monitor logs** for authentication failures

## Support

For more detailed information, see:
- [OAUTH_MIGRATION.md](./OAUTH_MIGRATION.md) - Complete migration guide
- [README.md](./README.md) - Application documentation
- SmartThings API Docs: https://developer-preview.smartthings.com/docs/

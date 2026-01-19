# Quick Reference: OAuth Setup for Local NAS

## TL;DR

Since your python-utility runs on a **local NAS** (not internet-accessible), it uses a **manual OAuth flow** with an external callback page.

## Setup (5 Minutes)

### 1. Register OAuth App
Go to: https://smartthings.developer.samsung.com/

```
Redirect URI: https://tatuvlak.github.io/tv-weather-oauth/callback.html
Scopes: r:devices:*, x:devices:*
```

Copy your `Client ID` and `Client Secret`

### 2. Configure Environment

Edit `/share/Container/tv-app-launcher/.env`:

```env
ST_CLIENT_ID=your-client-id-here
ST_CLIENT_SECRET=your-client-secret-here
OAUTH_REDIRECT_URI=https://tatuvlak.github.io/tv-weather-oauth/callback.html
SECRET_KEY=make-this-random
```

### 3. Deploy

```bash
cd /share/Container/tv-app-launcher
docker-compose down
docker-compose up --build -d
```

### 4. Authorize (One-Time)

**Step 1:** Get authorization URL
```bash
curl http://YOUR-NAS-IP:5000/oauth/authorize
```

**Step 2:** Copy the `authorization_url` from response

**Step 3:** Open that URL in your browser (any device)

**Step 4:** Log in to SmartThings and grant permissions

**Step 5:** You'll see a page with a code - copy it

**Step 6:** Submit the code
```bash
curl -X POST http://YOUR-NAS-IP:5000/oauth/token \
  -H "Content-Type: application/json" \
  -d '{"code":"PASTE-CODE-HERE"}'
```

**Done!** Check status:
```bash
curl http://YOUR-NAS-IP:5000/config
```

## Usage Examples

### Launch TV App
```bash
curl -X POST http://YOUR-NAS-IP:5000/launch-tv-app \
  -H "Content-Type: application/json" \
  -d '{"target_device": "s95"}'
```

### Check Health
```bash
curl http://YOUR-NAS-IP:5000/health
```

### View Configuration
```bash
curl http://YOUR-NAS-IP:5000/config
```

## Architecture

```
You (Browser) → SmartThings → GitHub Pages Callback → Copy Code
  ↓
You (Terminal) → POST code to NAS → NAS exchanges code for tokens
  ↓
Tokens saved → Auto-refresh forever
```

## Why External Callback?

- Your NAS is **not internet-accessible**
- SmartThings **cannot** callback to `http://nas-ip:5000/...`
- Solution: Use **GitHub Pages** as public callback
- Same pattern as your Samsung TV Weather App
- You manually copy the code (one-time setup)

## Troubleshooting

### "redirect_uri_mismatch"
Check redirect URI in SmartThings Developer Workspace:
- Must be: `https://tatuvlak.github.io/tv-weather-oauth/callback.html`
- No trailing slash, exact match

### "No authentication token available"
Run the authorization flow again (steps 4.1-4.6 above)

### "Token refresh failed"
```bash
# Check logs
docker logs tv-app-launcher

# Re-authorize if needed
curl http://YOUR-NAS-IP:5000/oauth/authorize
# ... follow steps again
```

### Tokens not persisting
```bash
# Check volume mount
docker inspect tv-app-launcher | grep -A 5 Mounts

# Ensure directory exists
mkdir -p /share/Container/tv-app-launcher/data
```

## Token Lifecycle

- **Access Token**: 24 hours
- **Refresh**: Automatic (5 min before expiry)
- **Storage**: `/app/data/oauth_tokens.json`
- **Persistence**: Survives container restarts

## Files & Docs

- **Quick Start**: [OAUTH_SETUP.md](./OAUTH_SETUP.md)
- **Migration**: [OAUTH_MIGRATION.md](./OAUTH_MIGRATION.md)
- **API Docs**: [README.md](./README.md)
- **Architecture**: [EXTERNAL_CALLBACK_ARCHITECTURE.md](./EXTERNAL_CALLBACK_ARCHITECTURE.md)

## Support

Check logs:
```bash
docker logs -f tv-app-launcher
```

View token status:
```bash
curl http://YOUR-NAS-IP:5000/config | python -m json.tool
```

Check token file:
```bash
docker exec tv-app-launcher cat /app/data/oauth_tokens.json | python -m json.tool
```

## Security Notes

- ✅ Tokens stored in persistent file (not environment)
- ✅ Automatic token refresh
- ✅ Client secret never exposed to browser
- ⚠️ Never commit `.env` or `oauth_tokens.json` to git
- ⚠️ Use strong `SECRET_KEY` in production

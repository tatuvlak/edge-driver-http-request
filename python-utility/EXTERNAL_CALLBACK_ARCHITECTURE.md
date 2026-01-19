# External OAuth Callback Architecture

## Problem

The python-utility service runs on a local NAS that is:
- Not accessible from the internet
- Behind a firewall/router
- Has only local network access

SmartThings OAuth requires a **redirect URI** where it can send the authorization code after the user grants permission. Since the NAS is not publicly accessible, SmartThings cannot directly callback to `http://local-nas:5000/oauth/callback`.

## Solution: External Callback Page

We reuse the **tv-weather-oauth** project - a static HTML page hosted on GitHub Pages that serves as the OAuth callback endpoint.

### Architecture Flow

```
┌─────────────┐
│   User      │
│  (Browser)  │
└──────┬──────┘
       │
       │ 1. Request auth URL
       ├──────────────────────────────────────────────┐
       │                                              │
       │                                    ┌─────────▼──────────┐
       │                                    │   NAS Service      │
       │                                    │ (Local Network)    │
       │                                    │ :5000              │
       │                                    └─────────┬──────────┘
       │                                              │
       │ 2. Returns authorization URL                 │
       │◄─────────────────────────────────────────────┘
       │
       │ 3. Opens auth URL in browser
       ├────────────────────────────────┐
       │                                │
       │                      ┌─────────▼──────────┐
       │                      │  SmartThings       │
       │                      │  OAuth Server      │
       │                      │  (Internet)        │
       │                      └─────────┬──────────┘
       │                                │
       │ 4. User authorizes             │
       │◄───────────────────────────────┘
       │
       │ 5. Redirects to callback with code
       ├─────────────────────────────────────────┐
       │                                         │
       │                               ┌─────────▼──────────┐
       │                               │  GitHub Pages      │
       │                               │  Callback Page     │
       │ 6. Displays code              │  (Internet)        │
       │◄──────────────────────────────┤                    │
       │                               └────────────────────┘
       │
       │ 7. User copies code
       │
       │ 8. POSTs code to /oauth/token
       ├──────────────────────────────────────────────┐
       │                                              │
       │                                    ┌─────────▼──────────┐
       │                                    │   NAS Service      │
       │                                    │ Exchanges code     │
       │                                    │ for tokens         │
       │                                    └─────────┬──────────┘
       │                                              │
       │ 9. Tokens saved, returns success             │
       │◄─────────────────────────────────────────────┘
       │
```

### Key Components

#### 1. GitHub Pages Callback (`tv-weather-oauth/callback.html`)
- **URL**: `https://tatuvlak.github.io/tv-weather-oauth/callback.html`
- **Purpose**: Receive OAuth redirect from SmartThings
- **Function**: 
  - Extract `code` parameter from URL
  - Display code in user-friendly format
  - Provide copy-to-clipboard functionality
  - Static HTML - no server-side processing

#### 2. NAS Service OAuth Endpoints

##### `GET /oauth/authorize`
- **Returns**: Authorization URL and instructions
- **Response**:
  ```json
  {
    "authorization_url": "https://api.smartthings.com/oauth/authorize?...",
    "callback_url": "https://tatuvlak.github.io/tv-weather-oauth/callback.html",
    "token_endpoint": "/oauth/token",
    "instructions": [...]
  }
  ```

##### `POST /oauth/token`
- **Accepts**: `{"code": "authorization-code"}`
- **Function**: Exchange code for access/refresh tokens
- **Process**:
  1. Receives authorization code from user
  2. Makes server-to-server call to SmartThings token endpoint
  3. Exchanges code for access and refresh tokens
  4. Saves tokens to `/app/data/oauth_tokens.json`
  5. Returns success with expiration info

### Workflow Steps

#### Initial Setup (One-Time)

1. **Register OAuth App** in SmartThings Developer Workspace
   - Set redirect URI: `https://tatuvlak.github.io/tv-weather-oauth/callback.html`
   - This is the publicly accessible callback URL

2. **Configure NAS Service**
   ```env
   ST_CLIENT_ID=your-client-id
   ST_CLIENT_SECRET=your-client-secret
   OAUTH_REDIRECT_URI=https://tatuvlak.github.io/tv-weather-oauth/callback.html
   ```

#### Authorization Flow (When Tokens Needed)

1. **User requests auth URL** from NAS:
   ```bash
   curl http://nas:5000/oauth/authorize
   ```

2. **NAS returns authorization URL** with proper redirect_uri parameter

3. **User opens URL** in browser (can be on any device)

4. **SmartThings authenticates** user and shows permission grant screen

5. **User grants permissions**

6. **SmartThings redirects** to GitHub Pages:
   ```
   https://tatuvlak.github.io/tv-weather-oauth/callback.html?code=ABC123...
   ```

7. **GitHub Pages displays code** in large, copy-friendly format

8. **User copies code** and submits to NAS:
   ```bash
   curl -X POST http://nas:5000/oauth/token \
     -H "Content-Type: application/json" \
     -d '{"code":"ABC123..."}'
   ```

9. **NAS exchanges code** for tokens via direct API call to SmartThings

10. **Tokens saved** to persistent storage

11. **Future requests** automatically use and refresh these tokens

### Why This Works

#### No Public Access Required
- NAS doesn't need to be internet-accessible
- OAuth redirect goes to GitHub Pages (always accessible)
- User manually bridges the gap by copying the code

#### Secure
- Authorization code is short-lived (typically 10 minutes)
- Code can only be exchanged once
- Token exchange happens server-to-server (NAS ↔ SmartThings)
- Client secret never exposed to browser

#### Reusable
- Same callback page works for multiple applications
- Used by both Samsung TV Weather App and python-utility
- No maintenance required (static page)

#### User-Friendly
- Clear visual feedback on callback page
- Copy-to-clipboard functionality
- Step-by-step instructions
- Works on any device with a browser

### Comparison to Direct Callback

#### Traditional OAuth (Requires Public Access)
```
User → SmartThings → Service Callback → Automatic token exchange → Done
```

#### Manual OAuth (Works on Local NAS)
```
User → SmartThings → GitHub Pages → User copies code → 
  User submits to NAS → Token exchange → Done
```

The extra manual step is the trade-off for not requiring public internet access.

### Alternative Considered: OAuth Out-of-Band (OOB)

SmartThings used to support `urn:ietf:wg:oauth:2.0:oob` which would display the code directly on SmartThings website instead of redirecting. However:
- Many OAuth providers are deprecating OOB flow
- Custom callback page provides better UX
- Already implemented for TV Weather app

### Maintenance

The external callback page requires:
- ✅ No server maintenance (static HTML)
- ✅ No SSL certificate management (GitHub Pages handles it)
- ✅ No scaling concerns (GitHub Pages CDN)
- ✅ No cost (GitHub Pages is free)

### Related Projects

This pattern is used in:
1. **samsung-tv-weather-app** - Tizen app OAuth
   - Same callback URL
   - Same manual flow
   - User copies code into TV app

2. **edge-driver-http-request/python-utility** - This service
   - Same callback URL
   - Same manual flow
   - User copies code via curl/API

Both benefit from sharing the same callback infrastructure.

## Implementation Notes

### SmartThings OAuth Registration

When registering in SmartThings Developer Workspace:

```
Application Name: TV App Launcher (or any name)
Redirect URI: https://tatuvlak.github.io/tv-weather-oauth/callback.html
Scopes: r:devices:*, x:devices:*
```

**Important**: The redirect URI must match **exactly** in:
- SmartThings OAuth client registration
- NAS service `OAUTH_REDIRECT_URI` environment variable
- Authorization URL construction

### Token Storage

Tokens are stored in `/app/data/oauth_tokens.json`:
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_at": 1737456789,
  "updated_at": "2026-01-19T..."
}
```

This file:
- Persists across container restarts (Docker volume)
- Contains sensitive credentials (proper permissions required)
- Auto-updated when tokens refresh

### Future Improvements

Potential enhancements:
1. **QR Code**: Display QR code in callback page for mobile scanning
2. **Auto-Submit**: Callback page could POST directly to NAS (if CORS allows)
3. **Webhook**: Use a temporary webhook service instead of manual copy
4. **Local Proxy**: Run temporary local proxy during auth flow

However, the current manual approach is:
- Simple and reliable
- Already implemented and tested
- No additional dependencies
- Works across all scenarios

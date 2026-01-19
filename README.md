# TV App Launcher - SmartThings Integration

This project enables launching a Samsung TV app through SmartThings routines using:
1. **SmartThings Edge Driver** - Runs on SmartThings Hub
2. **Python Utility** - Runs as Docker container on QNAP NAS

## Architecture

```
SmartThings Routine
    ↓
Edge Driver (Hub)
    ↓ HTTP Request
Python Utility (QNAP NAS)
    ↓ SmartThings API
Samsung TV → Launches Weather App
```

## Prerequisites

### For Edge Driver
- SmartThings Hub (v2 or v3)
- SmartThings CLI installed ([Installation Guide](https://github.com/SmartThingsCommunity/smartthings-cli))
- SmartThings account

### For Python Utility
- QNAP NAS with Container Station
- Docker and Docker Compose
- SmartThings Personal Access Token (for testing) or OAuth credentials
- Network connectivity between SmartThings Hub and QNAP NAS

## Setup Instructions

### Part 1: Python Utility on QNAP NAS

#### 1. Get Required Information

**SmartThings Personal Access Token:**
1. Go to https://account.smartthings.com/tokens
2. Create new token with these scopes:
   - `r:devices:*`
   - `x:devices:*`
3. Copy the token - you'll need it in the next step

**TV Device ID:**
```bash
# Using SmartThings CLI
smartthings devices --token=YOUR_PAT

# Or via API
curl -H "Authorization: Bearer YOUR_PAT" \
  https://api.smartthings.com/v1/devices
```

**TV App ID:**
- This is your Tizen app ID (e.g., `com.yourcompany.weatherapp`)
- Found in your app's `config.xml` or Tizen Studio

#### 2. Deploy on QNAP NAS

1. Copy the `python-utility` folder to your QNAP NAS:
   ```bash
   # Example using SCP
   scp -r python-utility admin@YOUR_NAS_IP:/share/Container/tv-app-launcher
   ```

2. SSH into your QNAP NAS:
   ```bash
   ssh admin@YOUR_NAS_IP
   cd /share/Container/tv-app-launcher
   ```

3. Create `.env` file:
   ```bash
   cp .env.example .env
   nano .env
   ```

   **QNAP Container Station note:** when importing the compose file, Container Station copies it to a temporary location. The `env_file: .env` entry expects the `.env` file to be in the same folder as the compose file. Ensure the `.env` file exists in the same directory you import, or change `env_file` to an absolute path on your NAS (e.g., `/share/Container/tv-app-launcher/.env`).

4. Edit `.env` with your values:
   ```env
   SMARTTHINGS_PAT=your-actual-pat-token
   TV_DEVICE_ID=your-tv-device-id
   TV_APP_ID=your-weather-app-id
   HOST=0.0.0.0
   PORT=5000
   ```

5. Build and run the container:
   ```bash
   docker-compose up -d
   ```

6. Check if it's running:
   ```bash
   docker-compose ps
   docker-compose logs -f
   ```

7. Test the health endpoint:
   ```bash
   curl http://localhost:5000/health
   ```

8. Test launching the app:
   ```bash
   curl -X POST http://localhost:5000/launch-tv-app \
     -H "Content-Type: application/json" \
     -d '{"action": "launch"}'
   ```

#### 3. Find Your NAS IP Address

You'll need this for the Edge Driver configuration:
```bash
ip addr show
# or
ifconfig
```

Look for your local network IP (usually 192.168.x.x or 10.0.x.x)

### Part 2: SmartThings Edge Driver

#### 1. Install SmartThings CLI

Windows PowerShell:
```powershell
npm install -g @smartthings/cli
```

#### 2. Login to SmartThings

```bash
smartthings login
```

Follow the prompts to authenticate.

#### 3. Package and Upload the Edge Driver

Navigate to the edge-driver folder:
```bash
cd edge-driver
```

Create a channel (first time only):
```bash
smartthings edge:channels:create
```

Note the channel ID from the output.

Package and upload:
```bash
# Package the driver
smartthings edge:drivers:package .

# Upload to your channel
smartthings edge:drivers:publish --channel=YOUR_CHANNEL_ID
```

#### 4. Install Driver on Hub

```bash
# Subscribe to your channel
smartthings edge:channels:assign --channel=YOUR_CHANNEL_ID

# Or use the SmartThings app:
# 1. Open SmartThings app
# 2. Go to Settings → Hub → Driver
# 3. Add channel using the channel ID
```

#### 5. Add Virtual Device

**Via SmartThings App:**
1. Open SmartThings app
2. Tap "+" → "Add Device"
3. Tap "Scan for nearby devices"
4. Wait for "TV App Launcher" to appear
5. Tap to add it

**Via CLI:**
```bash
smartthings devices:create
```

#### 6. Configure the Device

1. In SmartThings app, go to the "TV App Launcher" device
2. Tap the three dots (⋮) → "Settings"
3. Enter your QNAP NAS server URL: `http://192.168.1.100:5000` (use your actual NAS IP)
4. Save

### Part 3: Testing

#### Test the Edge Driver

1. Open SmartThings app
2. Go to "TV App Launcher" device
3. Tap the switch to turn it ON
4. Your TV should turn on and launch the weather app

#### Check Logs

**Python Utility:**
```bash
# On QNAP NAS
docker-compose logs -f
```

**Edge Driver:**
```bash
smartthings edge:drivers:logcat
```

### Part 4: Use in Routines

1. Open SmartThings app
2. Go to "Routines"
3. Create a new routine
4. Add action: "Control devices"
5. Select "TV App Launcher"
6. Choose "Turn on"
7. Save routine

Now you can trigger this routine to launch your TV app!

## Troubleshooting

### Python Utility Issues

**Container won't start:**
```bash
docker-compose logs
# Check for missing environment variables
```

**Can't reach utility from Edge Driver:**
- Verify firewall allows port 5000
- Check NAS IP address is correct
- Test from another device: `curl http://NAS_IP:5000/health`

**SmartThings API errors:**
- Verify PAT token is valid and has correct scopes
- Check TV_DEVICE_ID is correct
- Ensure TV is on the network

### Edge Driver Issues

**Device won't pair:**
- Restart SmartThings Hub
- Check driver is installed: `smartthings edge:drivers:installed`
- Check hub logs

**HTTP request fails:**
- Check server URL in device settings
- Ensure NAS is reachable from hub
- Check NAS firewall settings

## Upgrading to OAuth (Future)

When ready to switch from PAT to OAuth:

1. Register SmartThings app at https://smartthings.developer.samsung.com/
2. Get OAuth credentials (client ID, secret)
3. Implement OAuth flow from your TV app code
4. Update `.env` with OAuth credentials
5. In `app.py`, change `SmartThingsAPI(use_oauth=True)`

The OAuth refresh logic is already implemented in the utility.

## File Structure

```
edge-driver-http-request/
├── edge-driver/              # SmartThings Edge Driver
│   ├── src/
│   │   └── init.lua         # Main driver code
│   ├── config/
│   │   ├── config.yml       # Driver configuration
│   │   └── fingerprints.yml # Device fingerprints
│   └── profiles/
│       └── tv-app-launcher-profile.yml
│
└── python-utility/           # Python service for QNAP
    ├── app.py               # Flask application
    ├── requirements.txt     # Python dependencies
    ├── Dockerfile           # Docker image
    ├── docker-compose.yml   # Docker Compose config
    ├── .env.example         # Environment template
    └── .gitignore
```

## API Endpoints

### Python Utility

- `GET /health` - Health check
- `POST /launch-tv-app` - Launch TV app (called by Edge Driver)
- `GET /device-status` - Get TV device status
- `GET /config` - Get current configuration

## Security Notes

- Keep your `.env` file secure - never commit it to version control
- Use OAuth for production instead of PAT
- Consider using HTTPS if exposing outside local network
- Restrict network access to the utility to your local network only

## Support

For issues related to:
- **SmartThings Edge Drivers**: https://community.smartthings.com/
- **SmartThings API**: https://developer.smartthings.com/
- **QNAP Container Station**: QNAP support forums

## License

This project is for personal use. Ensure compliance with SmartThings and Samsung terms of service.

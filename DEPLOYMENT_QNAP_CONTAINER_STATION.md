# Deploy to QNAP Using Container Station GUI

Since `docker-compose` isn't available on your NAS, use Container Station's built-in GUI instead.

## Step 1: Upload Files to QNAP

### Using File Station (Recommended)

1. Open **QNAP File Station** in browser
2. Navigate to `/Container` folder (or create it)
3. Create new folder: `tv-app-launcher`
4. Upload these files from `python-utility` folder:
   - `app.py`
   - `requirements.txt`
   - `Dockerfile`
   - `.env` (**IMPORTANT - contains your credentials**)

### Alternative: Using Windows File Explorer

1. Open Windows File Explorer
2. In address bar type: `\\YOUR_QNAP_IP\Container`
3. Enter QNAP credentials when prompted
4. Create folder `tv-app-launcher`
5. Copy files from `python-utility` folder

## Step 2: Verify .env File on QNAP

Via SSH:
```bash
ssh admin@YOUR_QNAP_IP
cat /share/Container/tv-app-launcher/.env
```

Should show:
```env
SMARTTHINGS_PAT=<YOUR_PAT_TOKEN>
TV_DEVICE_ID_S95=<YOUR_S95_DEVICE_ID>
TV_DEVICE_ID_M7=<YOUR_M7_DEVICE_ID>
TV_APP_ID=tvweather1.tvweather
ST_CLIENT_ID=<YOUR_CLIENT_ID>
ST_CLIENT_SECRET=<YOUR_CLIENT_SECRET>
ST_REFRESH_TOKEN=
HOST=0.0.0.0
PORT=5000
```

## Step 3: Build Docker Image Using Container Station

1. Open **Container Station** app on QNAP
2. Go to **Images** tab
3. Click **Build** (top right)
4. Fill in the form:
   - **Image Name**: `tv-app-launcher`
   - **Tag**: `latest`
   - **Dockerfile Path**: Select `/Container/tv-app-launcher/Dockerfile`
   - **Build Context**: `/Container/tv-app-launcher`
5. Click **Build**
6. Wait for build to complete (2-5 minutes)
   - You'll see build logs in real-time
   - Should end with "Successfully built..."

## Step 4: Create Container from Image

1. Still in **Container Station**, go to **Images** tab
2. Find your `tv-app-launcher:latest` image
3. Click **Create Container** (play icon)
4. Fill in the form:

### Basic Settings
- **Name**: `tv-app-launcher`
- **Image**: `tv-app-launcher:latest` (should be pre-filled)

### Network Settings
- **Network Mode**: Bridge
- **Port Forwarding**: Click **Add**
  - **Container Port**: `5000`
  - **Host Port**: `5000`
  - **Type**: TCP

### Environment Variables
Click **Add** for each variable from your `.env` file:

| Variable Name | Value |
|---------------|-------|
| SMARTTHINGS_PAT | `<YOUR_PAT_TOKEN>` |
| TV_DEVICE_ID_S95 | `<YOUR_S95_DEVICE_ID>` |
| TV_DEVICE_ID_M7 | `<YOUR_M7_DEVICE_ID>` |
| TV_APP_ID | `tvweather1.tvweather` |
| ST_CLIENT_ID | `<YOUR_CLIENT_ID>` |
| ST_CLIENT_SECRET | `<YOUR_CLIENT_SECRET>` |
| ST_REFRESH_TOKEN | (leave empty) |
| HOST | `0.0.0.0` |
| PORT | `5000` |

### Advanced Settings (Optional)
- **Auto Restart**: Enable (to start on NAS reboot)
- **CPU Limit**: 0.5 (optional, to prevent high CPU usage)
- **Memory Limit**: 256 MB (optional)

5. Click **Create**

## Step 5: Verify Container is Running

1. Go to **Containers** tab in Container Station
2. Find `tv-app-launcher`
3. Status should show **Running** with green icon
4. Click on container name to see details
5. Click **Logs** tab to see output

**Expected logs:**
```
============================================================
TV App Launcher Utility Starting
============================================================
Host: 0.0.0.0
Port: 5000
TV Device ID (S95): 86cde607...
TV Device ID (M7): 1d5476d7...
TV App ID: tvweather1.tvweather
Auth Method: PAT
Auth Configured: True
============================================================
Running on http://0.0.0.0:5000
```

## Step 6: Test the Service

### From QNAP SSH:
```bash
curl http://localhost:5000/health
```

Should return:
```json
{"status":"healthy","timestamp":"...","version":"1.0.0"}
```

### From Windows PC:
```powershell
Invoke-RestMethod -Uri "http://YOUR_QNAP_IP:5000/health"
```

### Test Configuration:
```powershell
Invoke-RestMethod -Uri "http://YOUR_QNAP_IP:5000/config"
```

Should show both S95 and M7 devices.

## Step 7: Update Edge Driver with QNAP URL

Your Edge driver is currently using `http://192.168.1.100:5000`. 

If your QNAP IP is different:
1. In SmartThings app, go to device settings
2. Update **Server URL** to: `http://YOUR_QNAP_IP:5000`
3. Save

Or update the default in the driver code and redeploy.

## Step 8: Test End-to-End

1. In SmartThings app, tap your **TV App Launcher** device
2. Turn switch **ON**
3. **Your TV should turn on and launch the weather app!**

Check Container Station logs if it doesn't work.

## Managing the Container

### Stop Container
Container Station → Containers → Select `tv-app-launcher` → Click **Stop**

### Start Container
Container Station → Containers → Select `tv-app-launcher` → Click **Start**

### Restart Container
Container Station → Containers → Select `tv-app-launcher` → Click **Restart**

### View Logs
Container Station → Containers → Click on `tv-app-launcher` → **Logs** tab

### Update Application Code

If you change `app.py`:

1. Stop and remove the old container
2. Delete the old image (Images tab)
3. Upload new `app.py` to QNAP
4. Rebuild image (Step 3)
5. Create new container (Step 4)

## Troubleshooting

### Build Fails

Check Dockerfile path is correct:
- Should be: `/Container/tv-app-launcher/Dockerfile`
- Not: `/share/Container/...` (Container Station uses `/Container` shorthand)

### Container Won't Start

1. Check logs in Container Station
2. Verify all environment variables are set
3. Check port 5000 isn't already in use

### Can't Access from Network

1. Verify port forwarding: Container Port `5000` → Host Port `5000`
2. Check QNAP firewall settings
3. Test from QNAP itself first: `curl http://localhost:5000/health`

### Health Check Fails

Check logs for Python errors:
```bash
ssh admin@YOUR_QNAP_IP
docker logs tv-app-launcher
```

Common issues:
- Missing environment variables
- Invalid PAT token
- Network connectivity to SmartThings API

## Next Steps

After successful deployment:
1. ✅ Container running and healthy
2. ✅ Test `/health` and `/config` endpoints
3. ✅ Update Edge driver with QNAP IP (if needed)
4. ✅ Test switch ON in SmartThings app
5. ✅ Verify TV launches app
6. ⏭️ Create SmartThings routines to trigger automatically

---

**Your QNAP IP:** Find it in QNAP Control Panel → System → General → Network

**Container running?** Test: `http://YOUR_QNAP_IP:5000/health`

# Build Docker Image on Windows and Import to QNAP

## Prerequisites
- Docker Desktop installed on Windows
- QNAP IP: <YOUR_QNAP_IP>
- QNAP Username: <YOUR_USERNAME>

---

## Step 1: Install Docker Desktop (FIRST TIME ONLY)

1. Download: https://www.docker.com/products/docker-desktop
2. Run installer, accept defaults
3. **Restart Windows** (required)
4. Start Docker Desktop application
5. Wait for Docker to fully start (whale icon in system tray should be steady, not animated)

---

## Step 2: Build Docker Image for Linux (QNAP)

Open PowerShell and run:

```powershell
# Navigate to project directory
cd $PWD\python-utility

# Build image for Linux (QNAP runs Linux, not Windows)
docker build --platform linux/amd64 -t tv-app-launcher:latest .
```

**Expected output:**
```
[+] Building 45.2s (10/10) FINISHED
 => [1/5] FROM docker.io/library/python:3.11-slim
 => [2/5] WORKDIR /app
 => [3/5] COPY requirements.txt .
 => [4/5] RUN pip install --no-cache-dir -r requirements.txt
 => [5/5] COPY app.py .
 => exporting to image
 => => naming to docker.io/library/tv-app-launcher:latest
Successfully built and tagged tv-app-launcher:latest
```

This takes **2-5 minutes** on first build (downloads Python base image).

---

## Step 3: Export Image to TAR File

```powershell
# Export the image
docker save tv-app-launcher:latest -o tv-app-launcher.tar

# Verify file created (should be ~180 MB)
ls tv-app-launcher.tar
```

**Expected output:**
```
Mode          LastWriteTime    Length Name
----          -------------    ------ ----
-a----   1/18/2026  8:00 PM  180000000 tv-app-launcher.tar
```

---

## Step 4: Transfer TAR File to QNAP

### Option A: Using SCP (Secure Copy)

```powershell
# Transfer to QNAP Container folder
scp tv-app-launcher.tar <YOUR_USERNAME>@<YOUR_QNAP_IP>:/share/Container/
```

Enter your QNAP password when prompted.

### Option B: Using File Explorer (GUI)

1. Open File Explorer
2. In address bar, type: `\\<YOUR_QNAP_IP>\Container`
3. Login with username `<YOUR_USERNAME>` and your password
4. Copy `tv-app-launcher.tar` to this folder
5. Wait for upload to complete (2-5 minutes)

---

## Step 5: Import Image in Container Station

1. Open **Container Station** on QNAP (web browser: http://<YOUR_QNAP_IP>:8080)
2. Click **Images** tab (left sidebar)
3. Click **Import** button (top right)
4. Click **Browse** button
5. Navigate to: `/Container/tv-app-launcher.tar`
6. Select the file and click **OK**
7. Click **Import** button
8. Wait for import to complete (1-2 minutes)

**Result:** You should see `tv-app-launcher:latest` in your images list with size ~180 MB.

---

## Step 6: Create Container from Image

1. In **Images** tab, find `tv-app-launcher:latest`
2. Click the **▶ (Play)** icon or **Action** → **Create Container**
3. Fill in the container creation form:

### General Settings
- **Container Name**: `tv-app-launcher`
- **Image**: `tv-app-launcher:latest` (pre-filled)

### Network Settings
- **Network Mode**: Bridge
- **Port Forwarding**: Click **Add** (➕)
  - **Container Port**: `5000`
  - **Host Port**: `5000`
  - **Type**: TCP

### Environment Variables
Click **Add** (➕) for EACH variable:

| Variable Name | Value |
|---------------|-------|
| `SMARTTHINGS_PAT` | `<YOUR_PAT_TOKEN>` |
| `TV_DEVICE_ID_S95` | `<YOUR_S95_DEVICE_ID>` |
| `TV_DEVICE_ID_M7` | `<YOUR_M7_DEVICE_ID>` |
| `TV_APP_ID` | `tvweather1.tvweather` |
| `ST_CLIENT_ID` | `<YOUR_CLIENT_ID>` |
| `ST_CLIENT_SECRET` | `<YOUR_CLIENT_SECRET>` |
| `ST_REFRESH_TOKEN` | (leave empty) |
| `HOST` | `0.0.0.0` |
| `PORT` | `5000` |

### Advanced Settings (Recommended)
- ✅ Enable **Auto Restart** (container starts when NAS reboots)
- **CPU Limit**: 0.5 or 50%
- **Memory Limit**: 256 MB

4. Click **Create** button at bottom

---

## Step 7: Verify Container is Running

1. Go to **Containers** tab (left sidebar)
2. Find `tv-app-launcher`
3. Status should show **Running** with green dot
4. Click on container name to open details
5. Click **Logs** tab

**Expected logs:**
```
============================================================
TV App Launcher Utility Starting
============================================================
Host: 0.0.0.0
Port: 5000
TV Device ID (S95): <YOUR_S95_DEVICE_ID>
TV Device ID (M7): <YOUR_M7_DEVICE_ID>
TV App ID: tvweather1.tvweather
Auth Method: PAT
Auth Configured: True
============================================================
Running on http://0.0.0.0:5000
```

---

## Step 8: Test the Service

### From Windows PowerShell:

```powershell
# Health check
Invoke-RestMethod -Uri "http://<YOUR_QNAP_IP>:5000/health"
```

**Expected response:**
```
status    : healthy
timestamp : 2026-01-18T...
version   : 1.0.0
```

### Test configuration:
```powershell
Invoke-RestMethod -Uri "http://<YOUR_QNAP_IP>:5000/config"
```

Should show both S95 and M7 devices configured.

---

## Step 9: Update SmartThings Edge Driver

Your Edge driver may be using an old server URL.

**Update to:** `http://<YOUR_QNAP_IP>:5000`

### Method 1: Update Device Settings (Easiest)
1. Open SmartThings app
2. Go to **TV App Launcher** device
3. Tap **⋮** (three dots) → **Settings**
4. Update **Server URL** to: `http://<YOUR_QNAP_IP>:5000`
5. Save

### Method 2: Update Driver Code
Edit `edge-driver/src/init.lua` line 18:
```lua
local DEFAULT_SERVER_URL = "http://<YOUR_QNAP_IP>:5000"
```

Then repackage and upload driver.

---

## Step 10: TEST! 🎉

1. Open SmartThings app
2. Go to **TV App Launcher** device
3. Turn the switch **ON**
4. **Your S95 TV should turn on and launch the weather app!**

---

## Troubleshooting

### Container won't start
Check logs in Container Station → Containers → tv-app-launcher → Logs

Common issues:
- Missing environment variables
- Port 5000 already in use
- Wrong image format (must be linux/amd64)

### Can't access from network
1. Test locally on QNAP first via SSH:
   ```bash
   curl http://localhost:5000/health
   ```
2. Check QNAP firewall allows port 5000
3. Verify port forwarding is correct (5000 → 5000)

### Health check fails
1. Check container logs for Python errors
2. Verify all environment variables are set correctly
3. Test SmartThings API connectivity:
   ```bash
   curl -H "Authorization: Bearer <YOUR_PAT_TOKEN>" \
     https://api.smartthings.com/v1/devices
   ```

---

## Quick Commands Reference

```powershell
# Build image
docker build --platform linux/amd64 -t tv-app-launcher:latest .

# Save to file
docker save tv-app-launcher:latest -o tv-app-launcher.tar

# Copy to QNAP
scp tv-app-launcher.tar <YOUR_USERNAME>@<YOUR_QNAP_IP>:/share/Container/

# Test service
Invoke-RestMethod -Uri "http://<YOUR_QNAP_IP>:5000/health"
```

---

## After Windows Restart

1. ✅ Start Docker Desktop (wait for it to fully start)
2. ✅ Open PowerShell
3. ✅ Follow Step 2 to build the image
4. ✅ Continue with remaining steps

**Container will auto-start on QNAP reboot** (if Auto Restart is enabled).

# Build Docker Image on Windows and Import to QNAP

If you prefer to build the Docker image on your Windows PC and transfer it to QNAP.

## Prerequisites

- Docker Desktop installed on Windows
- Network access to QNAP
- SSH or File Station access to QNAP

## Step 1: Build Docker Image on Windows

Open PowerShell on Windows:

```powershell
# Navigate to your project directory
cd "C:\Users\barte\Documents\Projekty\edge-driver-http-request\python-utility"

# Build the Docker image
docker build -t tv-app-launcher:latest .
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
```

Verify the image was created:
```powershell
docker images tv-app-launcher
```

Should show:
```
REPOSITORY          TAG       IMAGE ID       CREATED         SIZE
tv-app-launcher     latest    abc123def456   2 minutes ago   180MB
```

## Step 2: Export Docker Image to TAR File

```powershell
# Export the image to a tar file
docker save tv-app-launcher:latest -o tv-app-launcher.tar
```

This creates `tv-app-launcher.tar` in your current directory (about 180 MB).

Verify the file was created:
```powershell
ls tv-app-launcher.tar
```

## Step 3: Transfer TAR File to QNAP

### Option A: Using SCP (Secure Copy)

```powershell
# Transfer to QNAP
scp tv-app-launcher.tar admin@YOUR_QNAP_IP:/share/Container/
```

Enter your QNAP admin password when prompted.

### Option B: Using File Station (GUI)

1. Open QNAP File Station in browser
2. Navigate to `/Container` folder
3. Click **Upload** → **Upload Files**
4. Select `tv-app-launcher.tar`
5. Wait for upload to complete (may take 2-5 minutes)

### Option C: Using Windows Network Share

1. Open File Explorer
2. Navigate to: `\\YOUR_QNAP_IP\Container`
3. Enter QNAP credentials
4. Copy `tv-app-launcher.tar` to this location

## Step 4: Import Image in Container Station

### Method 1: Container Station GUI

1. Open **Container Station** on QNAP
2. Go to **Images** tab
3. Click **Import** (top right)
4. Click **Browse**
5. Navigate to `/Container/tv-app-launcher.tar`
6. Click **Import**
7. Wait for import to complete (1-2 minutes)

You should see `tv-app-launcher:latest` in your images list.

### Method 2: SSH Command Line

```bash
# SSH to QNAP
ssh admin@YOUR_QNAP_IP

# Import the image
docker load -i /share/Container/tv-app-launcher.tar
```

**Expected output:**
```
Loaded image: tv-app-launcher:latest
```

Verify:
```bash
docker images tv-app-launcher
```

## Step 5: Prepare Environment Variables File

Still in SSH session:

```bash
# Create directory for app data
mkdir -p /share/Container/tv-app-launcher
cd /share/Container/tv-app-launcher

# Create .env file
cat > .env << 'EOF'
SMARTTHINGS_PAT=71629d58-6900-4df1-b2b4-39525b4940ee
TV_DEVICE_ID_S95=86cde607-414a-a9aa-25fe-71fbeeb2c9f8
TV_DEVICE_ID_M7=1d5476d7-3fb3-3e5b-fa91-a1c0cfc05aa7
TV_APP_ID=tvweather1.tvweather
ST_CLIENT_ID=2fc15490-2e53-40d6-a4f3-b4ef5782acc3
ST_CLIENT_SECRET=35dfab34-988f-4794-b369-d912adc90b5f
ST_REFRESH_TOKEN=
HOST=0.0.0.0
PORT=5000
EOF
```

Verify:
```bash
cat .env
```

## Step 6: Create and Run Container

### Option A: Using Docker Command (SSH)

```bash
# Run the container
docker run -d \
  --name tv-app-launcher \
  --restart unless-stopped \
  -p 5000:5000 \
  --env-file /share/Container/tv-app-launcher/.env \
  tv-app-launcher:latest
```

Verify container is running:
```bash
docker ps | grep tv-app-launcher
```

View logs:
```bash
docker logs tv-app-launcher
```

### Option B: Using Container Station GUI

1. In Container Station, go to **Images** tab
2. Find `tv-app-launcher:latest`
3. Click **Create Container** (play icon)
4. Configure as described in DEPLOYMENT_QNAP_CONTAINER_STATION.md Step 4
5. Click **Create**

## Step 7: Test the Service

### From QNAP SSH:
```bash
curl http://localhost:5000/health
```

Should return:
```json
{"status":"healthy","timestamp":"2026-01-18T19:30:00Z","version":"1.0.0"}
```

### From Windows:
```powershell
Invoke-RestMethod -Uri "http://YOUR_QNAP_IP:5000/health"
```

### Test Configuration:
```powershell
Invoke-RestMethod -Uri "http://YOUR_QNAP_IP:5000/config"
```

### Test Launch (will actually launch TV app!):
```powershell
$body = @{
    action = "launch"
    target_device = "s95"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://YOUR_QNAP_IP:5000/launch-tv-app" -Method Post -ContentType "application/json" -Body $body
```

**Your S95 TV should turn on and launch the weather app!**

## Step 8: Integrate with Edge Driver

Your Edge driver is timing out because it's trying to connect to `http://192.168.1.100:5000`.

### Get Your QNAP IP

```bash
# On QNAP via SSH
hostname -I
```

### Update Edge Driver

If your QNAP IP is different from `192.168.1.100`:

#### Option 1: Update Device Settings (Easiest)
1. Open SmartThings app
2. Go to your TV App Launcher device
3. Tap **Settings** (3 dots)
4. Update **Server URL** to: `http://YOUR_ACTUAL_QNAP_IP:5000`
5. Save

#### Option 2: Update Driver Code
Edit `edge-driver/src/init.lua`:

```lua
local DEFAULT_SERVER_URL = "http://YOUR_ACTUAL_QNAP_IP:5000"
```

Then repackage and upload driver.

## Step 9: Test End-to-End

1. Open SmartThings app
2. Go to TV App Launcher device
3. Turn switch **ON**
4. **Your TV should turn on and launch the weather app!**

Check logs if it doesn't work:
```bash
docker logs tv-app-launcher -f
```

## Managing the Container

### View Logs
```bash
docker logs tv-app-launcher -f
# Press Ctrl+C to exit
```

### Stop Container
```bash
docker stop tv-app-launcher
```

### Start Container
```bash
docker start tv-app-launcher
```

### Restart Container
```bash
docker restart tv-app-launcher
```

### Remove Container
```bash
docker stop tv-app-launcher
docker rm tv-app-launcher
```

### Update Container with New Image

1. Build new image on Windows
2. Export and transfer to QNAP
3. Import new image
4. Stop and remove old container
5. Create new container from new image

```bash
# On QNAP
docker stop tv-app-launcher
docker rm tv-app-launcher
docker load -i /share/Container/tv-app-launcher-new.tar
docker run -d --name tv-app-launcher --restart unless-stopped -p 5000:5000 --env-file /share/Container/tv-app-launcher/.env tv-app-launcher:latest
```

## Troubleshooting

### Container Won't Start

Check logs:
```bash
docker logs tv-app-launcher
```

Common issues:
- Port 5000 already in use
- Missing environment variables
- .env file not found

### Can't Access from Network

Test locally first:
```bash
# On QNAP
curl http://localhost:5000/health
```

If that works, check:
1. QNAP firewall settings
2. Network connectivity
3. Correct IP address

From Windows:
```powershell
Test-NetConnection -ComputerName YOUR_QNAP_IP -Port 5000
```

### SmartThings API Errors

Check logs for authentication errors:
```bash
docker logs tv-app-launcher | grep -i error
```

Verify PAT token:
```bash
cat /share/Container/tv-app-launcher/.env | grep PAT
```

Test manually:
```bash
curl -H "Authorization: Bearer 71629d58-6900-4df1-b2b4-39525b4940ee" \
  https://api.smartthings.com/v1/devices
```

### Container Stops Unexpectedly

Check for errors:
```bash
docker logs tv-app-launcher --tail 100
```

Check container status:
```bash
docker inspect tv-app-launcher | grep -A 10 State
```

## Cleanup Old Image File

After successful import, you can delete the tar file to save space:

### On QNAP:
```bash
rm /share/Container/tv-app-launcher.tar
```

### On Windows:
```powershell
rm tv-app-launcher.tar
```

## Next Steps

1. ✅ Container running on QNAP
2. ✅ Health check responding
3. ✅ Edge driver configured with correct IP
4. ✅ Test TV launch
5. ⏭️ Create SmartThings routines for automation

---

**Advantages of this method:**
- Build on faster Windows PC
- Reproducible builds
- Can distribute to others
- Can push to Docker Hub for easy deployment

**Container running?** Test: `http://YOUR_QNAP_IP:5000/health`

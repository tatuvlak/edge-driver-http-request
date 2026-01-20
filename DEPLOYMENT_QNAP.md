# QNAP NAS Deployment Guide

Complete guide to deploy the TV App Launcher Python utility as a Docker container on your QNAP NAS.

## Prerequisites

- QNAP NAS (TS-251B or compatible)
- Container Station installed
- SSH access to NAS (optional but recommended)
- Network connectivity to SmartThings Hub

## Method 1: Deploy via SSH (Recommended)

### Step 1: Enable SSH on QNAP

1. Open **QNAP Control Panel**
2. Go to **Network & File Services** → **Telnet / SSH**
3. Enable **Allow SSH connection**
4. Note the SSH port (default: 22)
5. Click **Apply**

### Step 2: Connect to QNAP via SSH

From your Windows PC:

```powershell
ssh admin@YOUR_QNAP_IP
```

Enter your QNAP admin password when prompted.

### Step 3: Create Directory for the Application

```bash
# Navigate to Container shared folder
cd /share/Container

# Create directory for the app
mkdir -p tv-app-launcher
cd tv-app-launcher
```

### Step 4: Transfer Files to QNAP

You have several options:

#### Option A: Using SCP (from Windows PowerShell)

On your Windows PC (not in SSH session):

```powershell
cd "$PWD"

# Copy the entire python-utility folder
scp -r python-utility admin@YOUR_QNAP_IP:/share/Container/tv-app-launcher/
```

#### Option B: Using QNAP File Station (GUI)

1. Open QNAP File Station
2. Navigate to `/Container`
3. Create folder: `tv-app-launcher`
4. Upload these files from `python-utility` folder:
   - `app.py`
   - `requirements.txt`
   - `Dockerfile`
   - `docker-compose.yml`
   - `.env` (important!)

#### Option C: Manual File Creation via SSH

```bash
# In SSH session on QNAP
cd /share/Container/tv-app-launcher

# Create app.py
nano app.py
# Paste the content, then Ctrl+X, Y, Enter

# Create other files similarly
nano requirements.txt
nano Dockerfile
nano docker-compose.yml
nano .env
```

### Step 5: Verify .env File

**IMPORTANT:** Ensure your `.env` file has the correct values:

```bash
cat .env
```

Should show:
```env
SMARTTHINGS_PAT=<YOUR_PAT_TOKEN>
TV_DEVICE_ID=<YOUR_TV_DEVICE_ID>
TV_APP_ID=tvweather1.tvweather
ST_CLIENT_ID=<YOUR_CLIENT_ID>
ST_CLIENT_SECRET=<YOUR_CLIENT_SECRET>
ST_REFRESH_TOKEN=
HOST=0.0.0.0
PORT=5000
```

If you need to edit it:
```bash
nano .env
```

### Step 6: Build and Start the Docker Container

```bash
# Make sure you're in the app directory
cd /share/Container/tv-app-launcher

# Build and start the container
docker-compose up -d
```

The first time will take a few minutes as it downloads the Python image and builds the container.

### Step 7: Verify Container is Running

```bash
# Check container status
docker-compose ps

# Should show:
# NAME                  STATUS
# tv-app-launcher       Up X seconds
```

View logs:
```bash
docker-compose logs -f
```

You should see:
```
============================================================
TV App Launcher Utility Starting
============================================================
Host: 0.0.0.0
Port: 5000
TV Device ID: 1d5476d7...
TV App ID: tvweather1.tvweather
Auth Method: PAT
Auth Configured: True
============================================================
Running on http://0.0.0.0:5000
```

Press `Ctrl+C` to exit logs.

### Step 8: Test the Service

From the QNAP SSH session:

```bash
# Test health endpoint
curl http://localhost:5000/health

# Should return:
# {"status":"healthy","timestamp":"...","version":"1.0.0"}
```

From your Windows PC:

```powershell
# Replace with your QNAP IP
Invoke-RestMethod -Uri "http://YOUR_QNAP_IP:5000/health"
```

### Step 9: Get Your QNAP IP Address

If you don't know your QNAP IP:

```bash
ip addr show | grep inet
```

Look for something like `inet 192.168.1.100/24` on your main network interface.

## Method 2: Deploy via Container Station GUI

### Step 1: Transfer Files

Use File Station to upload the `python-utility` folder contents to `/Container/tv-app-launcher/`

### Step 2: Open Container Station

1. Open **Container Station** app on QNAP
2. Click **Create** → **Create Application**

### Step 3: Configure Application

1. **Name**: `tv-app-launcher`
2. Click **YAML** tab
3. Paste the contents of `docker-compose.yml`
4. Modify the paths if needed

### Step 4: Validate and Create

1. Click **Validate YAML**
2. If valid, click **Create**
3. Wait for container to start

### Step 5: View Logs

1. In Container Station, go to **Containers**
2. Find `tv-app-launcher`
3. Click **Details** → **Logs**

## Configuration

### Port Mapping

The default port is **5000**. If you need to change it:

**Edit docker-compose.yml:**
```yaml
ports:
  - "8080:5000"  # Use port 8080 externally
```

Then restart:
```bash
docker-compose down
docker-compose up -d
```

### Environment Variables

To update environment variables without rebuilding:

```bash
nano .env
# Make changes
docker-compose restart
```

## Managing the Container

### Stop the container
```bash
docker-compose stop
```

### Start the container
```bash
docker-compose start
```

### Restart the container
```bash
docker-compose restart
```

### View logs
```bash
docker-compose logs -f
```

### Stop and remove container
```bash
docker-compose down
```

### Rebuild after code changes
```bash
docker-compose build --no-cache
docker-compose up -d
```

## Firewall Configuration

Ensure port 5000 is accessible:

1. QNAP Control Panel → **Security** → **Firewall**
2. If firewall is enabled, add rule:
   - **Name**: TV App Launcher
   - **Port**: 5000
   - **Protocol**: TCP
   - **Action**: Allow
3. Click **Apply**

## Auto-Start on NAS Reboot

The `restart: unless-stopped` in docker-compose.yml ensures the container automatically starts when the NAS boots up.

To verify:
```bash
docker-compose ps
```

The **Restart Policy** should show `unless-stopped`.

## Testing the Deployment

### Test 1: Health Check

```bash
curl http://localhost:5000/health
```

### Test 2: Configuration

```bash
curl http://localhost:5000/config
```

Should show your TV device and app configured.

### Test 3: Launch TV App (Will actually launch!)

```bash
curl -X POST http://localhost:5000/launch-tv-app \
  -H "Content-Type: application/json" \
  -d '{"action":"launch"}'
```

**This will turn on your TV and launch the app!**

## Troubleshooting

### Container Won't Start

Check logs:
```bash
docker-compose logs
```

Common issues:
- Missing `.env` file
- Port 5000 already in use
- Invalid docker-compose.yml syntax

### Can't Access from Network

1. Verify QNAP IP:
   ```bash
   ip addr show
   ```

2. Check firewall:
   ```bash
   # On QNAP
   iptables -L -n | grep 5000
   ```

3. Test from QNAP itself:
   ```bash
   curl http://localhost:5000/health
   ```

4. Test from Windows:
   ```powershell
   Test-NetConnection -ComputerName YOUR_QNAP_IP -Port 5000
   ```

### SmartThings API Errors

Check logs:
```bash
docker-compose logs | grep ERROR
```

Verify credentials:
```bash
cat .env
```

Test PAT token manually:
```bash
curl -H "Authorization: Bearer YOUR_PAT_TOKEN" \
  https://api.smartthings.com/v1/devices
```

### Container Uses Too Much Resources

Check resource usage:
```bash
docker stats tv-app-launcher
```

To limit resources, edit `docker-compose.yml`:
```yaml
services:
  tv-app-launcher:
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 256M
```

## Updating the Application

When you make changes to the code:

### Update Just the Code

1. Edit `app.py` on QNAP or re-upload via SCP
2. Restart container:
   ```bash
   docker-compose restart
   ```

### Full Rebuild

```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Monitoring

### View Real-time Logs

```bash
docker-compose logs -f
```

### Check Container Status

```bash
docker-compose ps
docker inspect tv-app-launcher
```

### Monitor Resources

```bash
docker stats tv-app-launcher
```

## Backup

Backup your configuration:

```bash
cd /share/Container/tv-app-launcher
tar -czf tv-app-launcher-backup.tar.gz .
```

Copy backup to safe location:
```bash
cp tv-app-launcher-backup.tar.gz /share/Backup/
```

## Next Steps

After deployment:
1. ✅ Deploy to QNAP (this guide)
2. ⏭️ Verify service is accessible: `http://YOUR_QNAP_IP:5000/health`
3. ⏭️ Configure Edge Driver with this URL
4. ⏭️ Test the complete flow
5. ⏭️ Create SmartThings routines

---

**Container running successfully?** Next, configure your Edge Driver with: `http://YOUR_QNAP_IP:5000`

See **DEPLOYMENT_EDGE_DRIVER.md** for Edge Driver setup.

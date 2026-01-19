# Quick Deployment Checklist

Use this checklist to ensure everything is deployed correctly.

## Pre-Deployment

- [ ] Python utility tested locally and working
- [ ] SmartThings CLI installed (`npm install -g @smartthings/cli`)
- [ ] QNAP Container Station installed
- [ ] SSH enabled on QNAP (optional)
- [ ] Fresh PAT token obtained: `<YOUR_PAT_TOKEN>`

## Part 1: Deploy Python Utility to QNAP

**Target:** Get `http://YOUR_QNAP_IP:5000/health` responding

- [ ] **Transfer files to QNAP** (`/share/Container/tv-app-launcher/`)
  - [ ] app.py
  - [ ] requirements.txt
  - [ ] Dockerfile
  - [ ] docker-compose.yml
  - [ ] .env (with correct credentials)

- [ ] **SSH to QNAP**
  ```bash
  ssh admin@YOUR_QNAP_IP
  cd /share/Container/tv-app-launcher
  ```

- [ ] **Verify .env file**
  ```bash
  cat .env
  # Should show your PAT, device ID, app ID
  ```

- [ ] **Build and start container**
  ```bash
  docker-compose up -d
  ```

- [ ] **Check container status**
  ```bash
  docker-compose ps
  # STATUS should be "Up"
  ```

- [ ] **View logs**
  ```bash
  docker-compose logs -f
  # Should show: "Auth Configured: True"
  ```

- [ ] **Note your QNAP IP**
  ```bash
  ip addr show | grep "inet 192"
  # Example: 192.168.1.100
  ```

- [ ] **Test health endpoint**
  ```bash
  curl http://localhost:5000/health
  # Should return: {"status":"healthy",...}
  ```

- [ ] **Test from Windows**
  ```powershell
  Invoke-RestMethod -Uri "http://YOUR_QNAP_IP:5000/health"
  ```

## Part 2: Install Edge Driver on SmartThings Hub

**Target:** Virtual device created in SmartThings app

- [ ] **Login to SmartThings CLI**
  ```powershell
  smartthings login
  ```

- [ ] **Create channel**
  ```powershell
  smartthings edge:channels:create
  # Note the Channel ID!
  ```

- [ ] **Package driver**
  ```powershell
  cd "C:\Users\barte\Documents\Projekty\edge-driver-http-request\edge-driver"
  smartthings edge:drivers:package .
  ```

- [ ] **Publish driver**
  ```powershell
  smartthings edge:drivers:publish --channel=YOUR_CHANNEL_ID
  ```

- [ ] **Subscribe hub to channel**
  ```powershell
  smartthings edge:channels:assign --channel=YOUR_CHANNEL_ID
  # Select your hub
  ```

- [ ] **Wait 5-10 minutes** for driver to install

- [ ] **Add device in SmartThings app**
  - SmartThings App → Devices → + → Scan
  - Look for "TV App Launcher"
  - Add it

- [ ] **Configure device settings**
  - Device → ⋮ → Settings
  - Server URL: `http://YOUR_QNAP_IP:5000`
  - Save

## Part 3: Test Integration

- [ ] **Test from SmartThings App**
  - Tap device switch to ON
  - Check QNAP logs: `docker-compose logs -f`
  - Should see incoming request

- [ ] **Verify TV launches**
  - TV should turn on
  - Weather app should launch

- [ ] **Check logs on both sides**
  
  **Edge Driver logs:**
  ```powershell
  smartthings edge:drivers:logcat
  ```
  
  **Python utility logs:**
  ```bash
  docker-compose logs -f
  ```

## Part 4: Create SmartThings Routine

- [ ] **Create routine in SmartThings App**
  - Routines → + Create
  - Add condition (e.g., "When I arrive home")
  - Add action → Control devices → TV App Launcher → Turn On
  - Save

- [ ] **Test routine**
  - Manually trigger routine
  - Verify TV launches app

## Verification Checklist

All these should work:

- [ ] Health check: `http://YOUR_QNAP_IP:5000/health` returns `200 OK`
- [ ] Config check: `http://YOUR_QNAP_IP:5000/config` shows device configured
- [ ] Edge driver device appears in SmartThings app
- [ ] Toggling device switch sends request to QNAP
- [ ] QNAP receives request (visible in logs)
- [ ] TV turns on and launches weather app
- [ ] Routine can trigger the device

## Troubleshooting Quick Checks

### Python Utility Not Working

```bash
# On QNAP
docker-compose ps        # Is it running?
docker-compose logs      # Any errors?
cat .env                 # Correct credentials?
curl http://localhost:5000/health  # Works locally?
```

### Edge Driver Not Working

```powershell
# Check driver status
smartthings edge:drivers:installed

# View logs
smartthings edge:drivers:logcat

# Check device is online
smartthings devices
```

### Can't Connect

```powershell
# From Windows
Test-NetConnection -ComputerName YOUR_QNAP_IP -Port 5000
ping YOUR_QNAP_IP
```

```bash
# On QNAP
iptables -L -n | grep 5000  # Firewall blocking?
netstat -tlnp | grep 5000   # Is service listening?
```

## Success Indicators

✅ **QNAP:** Container shows "Up", logs show "Auth Configured: True"  
✅ **Edge Driver:** Device appears in app, configured with QNAP URL  
✅ **Integration:** Toggling switch launches TV app  
✅ **Routine:** Automation triggers TV app launch  

---

## Quick Reference

**QNAP IP:** `___________________`  
**Channel ID:** `___________________`  
**Device Name:** `___________________`  

**Useful Commands:**

```bash
# QNAP
docker-compose logs -f
docker-compose restart
docker-compose ps

# Windows
smartthings edge:drivers:logcat
Invoke-RestMethod http://YOUR_QNAP_IP:5000/health
```

---

**Everything working?** 🎉 You can now control your TV app through SmartThings routines!

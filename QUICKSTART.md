# Quick Start Guide

## TL;DR - Get it working in 5 steps

### Step 1: Get Your Credentials

1. **SmartThings PAT**: https://account.smartthings.com/tokens
   - Scopes needed: `r:devices:*`, `x:devices:*`
   
2. **TV Device ID**: 
   ```bash
   smartthings devices
   ```
   
3. **TV App ID**: Your Tizen app ID (e.g., `com.example.weatherapp`)

### Step 2: Deploy Python Utility on QNAP

```bash
# Copy files to QNAP
scp -r python-utility admin@YOUR_NAS_IP:/share/Container/

# SSH to QNAP
ssh admin@YOUR_NAS_IP
cd /share/Container/python-utility

# Create .env file
cp .env.example .env
nano .env  # Edit with your values

# Start container
docker-compose up -d

# Test it
curl http://localhost:5000/health
```

### Step 3: Get Your NAS IP

```bash
# On QNAP
ip addr show
```

Note the IP address (e.g., 192.168.1.100)

### Step 4: Install Edge Driver

```bash
# In edge-driver folder
cd edge-driver

# Login
smartthings login

# Create channel (first time only)
smartthings edge:channels:create

# Package and upload
smartthings edge:drivers:package .
smartthings edge:drivers:publish --channel=YOUR_CHANNEL_ID

# Install on hub
smartthings edge:channels:assign --channel=YOUR_CHANNEL_ID
```

### Step 5: Add Device & Configure

1. **SmartThings App** → "+" → "Add Device" → "Scan"
2. Add "TV App Launcher"
3. Device Settings → Enter server URL: `http://YOUR_NAS_IP:5000`
4. Tap the switch to test!

## Use in Routines

**SmartThings App** → Routines → New Routine → Add Action → TV App Launcher → Turn On

Done! 🎉

---

See [README.md](README.md) for detailed documentation.

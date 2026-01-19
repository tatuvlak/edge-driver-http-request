# Edge Driver Installation Guide

Complete guide to install the TV App Launcher Edge Driver on your SmartThings Hub.

## Prerequisites

- SmartThings Hub (v2 or v3)
- SmartThings CLI installed
- SmartThings account
- PC with Node.js installed (for SmartThings CLI)

## Step 1: Install SmartThings CLI

If you haven't already installed the SmartThings CLI:

```powershell
npm install -g @smartthings/cli
```

Verify installation:
```powershell
smartthings --version
```

## Step 2: Login to SmartThings

```powershell
smartthings login
```

This will open a browser window. Log in with your SmartThings account credentials.

## Step 3: Create an Edge Driver Channel

A channel is where your custom driver will be hosted.

```powershell
smartthings edge:channels:create
```

You'll be prompted to enter:
- **Name**: `TV App Launcher` (or any name you prefer)
- **Description**: `Custom driver for launching TV apps via HTTP`
- **Channel terms of service URL**: For personal use, you can use a placeholder like:
  - `https://www.smartthings.com/terms` (SmartThings terms)
  - `https://example.com/terms` (placeholder)
  - Or your own GitHub repo URL if you plan to share it

**Save the Channel ID** that's displayed - you'll need it! It looks like:
```
Channel ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

## Step 4: Package and Upload the Edge Driver

Navigate to the edge-driver folder:

```powershell
cd "C:\Users\barte\Documents\Projekty\edge-driver-http-request\edge-driver"
```

Package and upload the driver (this single command does both):

```powershell
smartthings edge:drivers:package .
```

The CLI will automatically upload the driver and display:
```
───────────────────────────────────────────────────
 Driver Id    xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
 Name         TV App Launcher
 Package Key  tv-app-launcher
 Version      2026-01-18T17:25:08.360279223
───────────────────────────────────────────────────
```

**Save the Driver ID** - you'll need it for troubleshooting.

## Step 5: Assign Driver to Your Channel

Assign the uploaded driver to your channel:

```powershell
smartthings edge:channels:assign
```

You'll be prompted to select:
1. **Driver**: Choose `TV App Launcher` (the one you just uploaded)
2. **Version**: Choose the version timestamp (e.g., `2026-01-18T17:25:08.360279223`)
3. **Channel**: Choose `TV App Launcher` (your channel from Step 3)

The CLI will confirm the assignment with a success message.

## Step 6: Subscribe Your Hub to the Channel

Enroll your hub in the channel:

```powershell
smartthings edge:channels:enroll
```

You'll be prompted to:
1. Select your channel (`TV App Launcher`)
2. Select your hub

The CLI will confirm enrollment.

**Or** subscribe via SmartThings mobile app:
1. Open **SmartThings app**
2. Go to **☰ Menu** → **Settings** → **Hubs**
3. Select your hub
4. Tap **Driver** (or **Edge Drivers**)
5. Tap **+** (or **Available Drivers**)
6. Find and tap your channel name
7. Tap **Install**

## Step 7: Install the Driver on Your Hub

After subscribing to the channel, install the driver:

```powershell
smartthings edge:drivers:install
```

Select:
1. Your driver from the list
2. Your hub

The driver will be installed to your hub (this may take a few minutes).

## Step 8: Repackage and Update the Driver

The driver now includes auto-device creation. Repackage and update:

```powershell
cd "C:\Users\barte\Documents\Projekty\edge-driver-http-request\edge-driver"
smartthings edge:drivers:package .
```

Then assign the new version to your channel:

```powershell
smartthings edge:channels:assign
```

Select the new version when prompted. The hub will automatically update the driver (may take a few minutes).

## Step 9: Check for the Device

After the driver updates, the device should automatically appear:

1. Open **SmartThings app**
2. Go to **Devices** tab
3. Look for **TV App Launcher**

If it doesn't appear after 5 minutes:
- Restart the hub (unplug for 30 seconds)
- Check driver logs: `smartthings edge:drivers:logcat`

## Step 10: Configure the Device

The device needs to know the URL of your Python utility on QNAP.

1. Open **SmartThings app**
2. Go to **Devices** → **TV App Launcher**
3. Tap **⋮** (three dots) → **Settings**
4. Find **Server URL** setting
5. Enter: `http://YOUR_QNAP_IP:5000`
   - Example: `http://192.168.1.100:5000`
6. Tap **Save**

**To find your QNAP IP:**
- QNAP Control Panel → Network & File Services → Network → TCP/IP
- Or via SSH: `ip addr show`

## Step 11: Test the Device

1. In SmartThings app, go to the device
2. Tap the **switch** to turn it ON
3. The device should send a request to your QNAP server
4. Check the Python utility logs to verify

## Troubleshooting

### Driver Not Installing

**Check driver status:**
```powershell
smartthings edge:drivers:installed
```

**Check hub logs:**
```powershell
smartthings edge:drivers:logcat
```

### Device Not Appearing

1. Wait 5-10 minutes after driver installation
2. Restart SmartThings Hub:
   - Unplug for 30 seconds
   - Plug back in
3. Try scanning again

### Can't Connect to Python Utility

1. Verify QNAP IP is correct
2. Ensure port 5000 is accessible:
   ```powershell
   Test-NetConnection -ComputerName YOUR_QNAP_IP -Port 5000
   ```
3. Check QNAP firewall settings
4. Verify Docker container is running on QNAP

## Updating the Driver

When you make changes to the driver code:

1. Package and upload again:
   ```powershell
   smartthings edge:drivers:package .
   ```

2. Assign the new version to your channel:
   ```powershell
   smartthings edge:channels:assign
   ```
   Select the new version when prompted.

3. The hub will automatically update (may take a few minutes)
4. Or restart the hub to force update

## Useful Commands

**View driver logs in real-time:**
```powershell
smartthings edge:drivers:logcat
```

**List all your channels:**
```powershell
smartthings edge:channels
```

**List installed drivers:**
```powershell
smartthings edge:drivers:installed
```

**Uninstall driver:**
```powershell
smartthings edge:drivers:uninstall
```

## Next Steps

After installing the Edge Driver:
1. ✅ Install Edge Driver (this guide)
2. ⏭️ Deploy Python utility to QNAP (see DEPLOYMENT_QNAP.md)
3. ⏭️ Test the integration
4. ⏭️ Create SmartThings routines

---

**Need help?** Check the SmartThings community: https://community.smartthings.com/

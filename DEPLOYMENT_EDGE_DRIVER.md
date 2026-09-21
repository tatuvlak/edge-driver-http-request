# Edge Driver Installation Guide

The driver is a virtual switch. A SmartThings routine cannot make an HTTP call
— it can only operate a device — so the driver presents itself as a switch
whose "on" means "POST to the weather service on the NAS, which opens the app
on the TV".

**Publishing goes through the SmartThings developer API, which becomes a paid
subscription in October 2026.** The driver itself runs on the hub and keeps
working regardless; it is the ability to *change* it that expires. Treat every
publish as possibly the last one, and put in anything the driver might ever
need rather than waiting until it is wanted.

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
cd "$PWD\edge-driver"
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
cd "$PWD\edge-driver"
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

1. Open **SmartThings app**
2. Go to **Devices** → **TV App Launcher**
3. Tap **⋮** (three dots) → **Settings**

| Preference | Set it to |
|---|---|
| **Server URL** | `http://<NAS address>:5000`, e.g. `http://192.168.18.250:5000` |
| **Target device** | Which display to launch on — S95 TV or M7 Monitor |
| **Action token** | Leave **blank** unless `ACTION_TOKEN` is set on the server. See below. |

**An existing device keeps the preferences it already had.** Changing a default
in the profile only affects a device added afterwards, so check these after
every update rather than assuming a new default applied.

**To find your QNAP address:** Control Panel → Network & File Services →
Network & Virtual Switch → TCP/IP. Give it a static address there if you can —
the NAS setting its own address needs no router access, and it saves both this
preference and the sensor's firmware from chasing DHCP.

### About the action token

`POST /launch-tv-app` is currently unauthenticated: the server's `ACTION_TOKEN`
is empty and this preference is blank, so anyone on the LAN can open an app on
the TV. That is a small risk while the service is LAN-only.

It stops being LAN-only when remote access arrives. The driver already sends
`Authorization: Bearer <token>` whenever this preference is non-empty, purely so
that switching it on later does **not** require republishing — which may no
longer be free. To enable it: set `ACTION_TOKEN` in the server's `.env`,
recreate the container, then paste the same value here. Set one without the
other and the launch fails with HTTP 401 or 403, which the driver log spells
out.

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

From the repository root, with `main` checked out and pulled:

```powershell
smartthings edge:drivers:package edge-driver/
smartthings edge:channels:assign
smartthings edge:drivers:install
```

`channels:assign` is the step that actually publishes the new version; pick it
when prompted. The hub picks it up within a few minutes.

Confirm which version is running rather than assuming:

```powershell
smartthings edge:drivers:logcat --hub-address=<hub IP>
```

The driver logs its version on startup, e.g. `TV App Launcher Edge Driver v1.1
Started`. If you see the previous version, the hub has not swapped yet.

Then fire the routine once and watch the same log. A working launch reaches the
service, which confirms the app is actually running on the display rather than
merely accepting the command.

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

1. Deploy the service — see
   [`DEPLOYMENT_QNAP_CONTAINER_STATION.md`](DEPLOYMENT_QNAP_CONTAINER_STATION.md)
2. Set the device preferences (Step 10)
3. Build a routine: turn the display on, then turn this switch on. The switch
   returns to off by itself after two seconds, so it can be triggered again.

---

**Need help?** Check the SmartThings community: https://community.smartthings.com/

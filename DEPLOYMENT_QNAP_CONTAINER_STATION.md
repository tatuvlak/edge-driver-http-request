# Deploy to QNAP Using Container Station GUI

Since `docker-compose` isn't available on your NAS, use Container Station's built-in GUI instead.

---

# Which deployment is live

**There are two folders on the NAS, and only one of them matters.**

| Folder | Compose file | What it is |
|---|---|---|
| `/Container/tv-app-launcher-no-api` | `docker-compose.no-api.yml` | **The live service.** Local control, weather hub. |
| `/Container/tv-app-launcher` | `docker-compose.yml` | The original SmartThings-API version. Stopped, kept as a rollback. |

This page used to name `tv-app-launcher` throughout, because it was written
before the second deployment existed. Following it put an update into the
stopped folder: the files landed, the rebuild succeeded, and the live service
went on running the old code with nothing to show anything had gone wrong.

**Confirm it from the filesystem rather than from this page.** The sensor posts
every few minutes, so the live database is the one that was written seconds
ago:

- `/Container/tv-app-launcher-no-api/data/weather.db`
- `/Container/tv-app-launcher/data/weather.db`

Compare their modification times in File Station. Cross-check in Container
Station -> Containers: one container is running and bound to host port 5000,
and its name is the answer.

Everything below says `tv-app-launcher-no-api`. If the check above disagrees,
trust the check and fix this page.

---

# Updating an existing deployment

Re-uploading the changed files is not enough, and neither is **Recreate** —
that rebuilds the container from the image it already has. The image itself has
to be rebuilt:

1. **Back up the database.** File Station -> copy
   `/Container/tv-app-launcher-no-api/data/weather.db` somewhere, dated.
   `weather_store.init()` migrates the schema in place on start.
2. **Upload the changed files** into `/Container/tv-app-launcher-no-api/`,
   flat at the top level. The Dockerfile's `COPY` reads that directory, so a
   file in a `python-utility/` subfolder is invisible to the build.
3. **Applications -> `tv-app-launcher-no-api` -> Delete.** The data is on the
   NAS, outside the container, and survives this.
4. **Applications -> Create**, same name, paste the whole of
   `python-utility/docker-compose.no-api.yml`. Check the pasted text says
   `-no-api` in `build.context`, the volume and `env_file`.
5. **Verify which code is running**, not just that it started:

   ```powershell
   curl.exe -s -H "Authorization: Bearer <READ_TOKEN>" "http://<nas>:5000/api/weather"
   ```

   `recorded_at` must carry a UTC offset - `2026-10-15T21:38:43+00:00`, not
   `2026-10-15T21:38:43`. A bare timestamp means the build predates that fix
   and the upload did not take effect.

A migration logs its one line on the start that performs it and never again, so
`Added column ... to readings` is a useful signal only on the first start after
an upgrade. The offset check above stays true permanently, which is why it is
the one to rely on.

---

# Rebuilding for the local-control version

**The history of how the live deployment came to exist.** For updating it, use
the section above. This version launches the app over the LAN instead of the
SmartThings cloud, and hosts the weather data the sensor pushes. Both change
what the container needs.

> The paths below say `tv-app-launcher` because that was the only folder when
> this was written. The live deployment is `tv-app-launcher-no-api`; substitute
> it anywhere a path appears.

Three things differ from the original setup below:

1. **More files.** The service is no longer a single `app.py`. `tv_local.py` and
   `weather_store.py` must be uploaded too, or the container dies on
   `ImportError` at start.
2. **A volume is now required.** The weather database and the cache of
   discovered display addresses live in `/app/data`. Without a volume they are
   wiped every time the container is recreated — you lose history and the
   service has to rescan for displays.
3. **Different environment variables.** LAN addresses and MACs replace the
   SmartThings device IDs, and there are API tokens.

## 1. Upload the changed files

File Station → `/Container/tv-app-launcher`, overwriting:

- `app.py`
- `tv_local.py`      *(new)*
- `weather_store.py` *(new)*
- `Dockerfile`       *(changed — copies the new modules, longer worker timeout)*
- `requirements.txt`

## 2. Create the data folder

In File Station, create `/Container/tv-app-launcher/data` if it does not exist.
This is what the volume in step 4 maps to.

## 3. Put the tokens and addresses in `.env`

Edit `/Container/tv-app-launcher/.env` (File Station, or SSH). Add:

```env
TV_HOST_S95=192.168.18.187
TV_MAC_S95=F0:70:4F:32:BF:DA
TV_HOST_M7=192.168.18.186
TV_MAC_M7=54:44:A3:5C:4B:16
TV_APP_ID=tvweather1.tvweather

INGEST_TOKEN=<generate one>
READ_TOKEN=<generate a different one>
ACTION_TOKEN=
```

Generate each token with
`python -c "import secrets; print(secrets.token_urlsafe(32))"`. **Do not reuse
one value for both** — the read token ships inside the app package on the TV, so
it must not be able to forge sensor readings.

**Leave `ACTION_TOKEN` empty.** The Edge driver sends no credentials, so setting
it breaks your routine until the driver is republished.

The old `SMARTTHINGS_PAT`, `ST_CLIENT_*` and `TV_DEVICE_ID_*` lines are no longer
read by the launch path. Harmless to leave, tidier to remove.

## 4. Build and run — Container Station 3.x

Newer Container Station has no **Build** button under Images (only Pull and
Import). Building happens through Applications instead, which reads a compose
file:

1. Container Station → **Applications** → **Create**
2. Name it `tv-app-launcher`
3. Paste the entire contents of `python-utility/docker-compose.yml`
4. **Create**

That builds the image from the Dockerfile and starts the container with the
port, the volume and the `.env` already wired up. If an old `tv-app-launcher`
container exists from the previous deployment, stop and delete it first —
the name would clash.

To apply later code changes: re-upload the files, then in Applications use
**Recreate** (or Stop → Start with rebuild). Editing files alone changes
nothing until the image is rebuilt.

> **Why the compose file has no `environment:` block.** Container Station copies
> the compose file to a temporary directory before running it, so `${VAR}`
> interpolation — which reads the `.env` next to the compose file — resolves to
> empty strings. Because `environment:` overrides `env_file:`, those blanks
> would win over the real values and the service would come up with nothing
> configured, while `.env` still looked correct. Configuration therefore comes
> from `env_file` alone, by absolute path.

### Older Container Station (Images → Build)

If your version does have **Build** under Images, that route still works:
build with Dockerfile and context both `/Container/tv-app-launcher`, then create
the container manually with port `5000` → `5000`, the volume
`/Container/tv-app-launcher/data` → `/app/data`, and every variable from step 3
entered by hand. Rebuilding an image does not update a running container — you
have to delete and recreate it.

### No GUI build at all? Use SSH

```bash
cd /share/Container/tv-app-launcher
docker build -t tv-app-launcher:latest .
docker rm -f tv-app-launcher 2>/dev/null
docker run -d --name tv-app-launcher --restart unless-stopped \
  -p 5000:5000 \
  -v /share/Container/tv-app-launcher/data:/app/data \
  --env-file /share/Container/tv-app-launcher/.env \
  tv-app-launcher:latest
```

The `docker` binary is present even on NAS models where `docker-compose` is not.

## 5. Verify

```bash
curl http://localhost:5000/health      # weather.has_readings, version 3.x
curl http://localhost:5000/displays    # both configured AND reachable
curl http://localhost:5000/config      # ingest and read should say "token required"
```

`/displays` is the one that matters: `reachable: false` means the NAS cannot see
that display, which is a network problem to solve before going further.

If `/config` reports `OPEN - set INGEST_TOKEN`, the variables did not reach the
container — check the container's Environment tab rather than the `.env` file,
since Container Station passes what is set in the GUI.

Then the data round trip:

```bash
curl -X POST http://localhost:5000/ingest \
  -H "Authorization: Bearer YOUR_INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '{"temperature_c":21.4,"humidity_pct":48,"aqi":1}'

curl -H "Authorization: Bearer YOUR_READ_TOKEN" http://localhost:5000/api/weather
```

Finally trigger the SmartThings routine — the display should power on and the
weather app open, with no SmartThings API call involved.

## If your Container Station has an "Applications" tab

Container Station 3.x can import a compose file directly, which avoids typing
every variable by hand: **Applications → Create**, paste the contents of
`docker-compose.yml`, and put the values in a `.env` beside it. The compose file
in this repo already carries the volume, ports and full variable list. The manual
route above works on every version, which is why it is written out in full.

---

# Original setup (SmartThings cloud version)

Kept for reference. The steps below still describe how building and creating a
container works, but the file list, volume and variables are superseded by the
section above.

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

-- SmartThings Edge Driver for TV App Launch
-- Sends HTTP request to local Python utility to launch TV app

local capabilities = require "st.capabilities"
local Driver = require "st.driver"
local cosock = require "cosock"
local socket = require "cosock.socket"
local http = cosock.asyncify "socket.http"
local ltn12 = require "ltn12"
local json = require "dkjson"
local log = require "log"

-- Module variables
local initialized = false

-- Configuration - these should be set via device preferences.
--
-- The fallback is only reached if serverUrl is somehow unset. It used to be
-- 192.168.1.100, a different subnet entirely, so a blank preference failed
-- silently into nowhere. Point it at the real NAS so the fallback is at least
-- plausible, and log loudly when it is used.
local DEFAULT_SERVER_URL = "http://192.168.18.250:5000"
local DEFAULT_ENDPOINT = "/launch-tv-app"

-- Bound the request. The utility can legitimately take a while when a display
-- has moved and it has to rediscover by MAC, and it waits for the set to
-- confirm the app is actually running - but "a while" must not mean forever.
-- The NAS is a general-purpose box that can get busy, and a request with no
-- timeout would leave the driver waiting on it indefinitely.
local REQUEST_TIMEOUT_SECONDS = 60

-- ---------------------------------------------------------------------------
-- Talking to the display directly
-- ---------------------------------------------------------------------------
-- The launch used to go entirely through the utility on the NAS, because the
-- original design needed it to hold a SmartThings token. It no longer does:
-- the television answers a plain HTTP POST on port 8001 with no
-- authentication, verified on both sets. So the hub can do it itself and the
-- NAS drops out of the common path.
--
-- Port 8001 rather than 8002 on purpose. 8002 is the same API over TLS with a
-- self-signed certificate, which would need luasec and verification disabled
-- inside the Edge sandbox. 8001 needs neither and does the same job.
local TV_PORT = 8001
local TV_TIMEOUT_SECONDS = 8

-- Both televisions have changed address twice in a fortnight; there are no
-- DHCP reservations on this network. So a cached address is a hint, never a
-- fact, and something has to find the set again when the hint goes stale.
local SSDP_ADDR, SSDP_PORT = "239.255.255.250", 1900
local SSDP_BUDGET_SECONDS = 4

local function normalise_mac(mac)
  if type(mac) ~= "string" then return nil end
  mac = mac:upper():gsub("-", ":"):gsub("%s", "")
  return mac ~= "" and mac or nil
end

-- Ask a host whether it is a Samsung television, and which one.
local function tv_identify(host)
  local body = {}
  http.TIMEOUT = 3
  local _, code = http.request({
    url = "http://" .. host .. ":" .. TV_PORT .. "/api/v2/",
    sink = ltn12.sink.table(body),
  })
  if code ~= 200 then return nil end
  local ok, parsed = pcall(json.decode, table.concat(body))
  if not ok or type(parsed) ~= "table" or type(parsed.device) ~= "table" then
    return nil
  end
  return normalise_mac(parsed.device.wifiMac), parsed.device.name
end

-- Open an app on a display. The set answers "true" on success.
local function tv_launch(host, app_id)
  local body = {}
  http.TIMEOUT = TV_TIMEOUT_SECONDS
  local _, code = http.request({
    url = "http://" .. host .. ":" .. TV_PORT .. "/api/v2/applications/" .. app_id,
    method = "POST",
    headers = { ["Content-Length"] = "0" },
    sink = ltn12.sink.table(body),
  })
  return code == 200, tostring(code)
end

-- Who is on the network? One multicast question instead of scanning 254
-- addresses, which is what the utility has to do and what would be unwise from
-- a hub.
--
-- Asks ssdp:all rather than the Samsung device type: probing this network for
-- urn:samsung.com:device:RemoteControlReceiver:1 returned nothing at all from
-- either set, while ssdp:all found both. So ask broadly and filter by MAC.
local function ssdp_search()
  local seen, hosts = {}, {}
  local udp = socket.udp()
  if not udp then return hosts end

  udp:setsockname("*", 0)
  udp:settimeout(1)
  udp:sendto(table.concat({
    "M-SEARCH * HTTP/1.1",
    "HOST: " .. SSDP_ADDR .. ":" .. SSDP_PORT,
    'MAN: "ssdp:discover"',
    "MX: 2",
    "ST: ssdp:all",
    "", "",
  }, "\r\n"), SSDP_ADDR, SSDP_PORT)

  local deadline = os.time() + SSDP_BUDGET_SECONDS
  while os.time() < deadline do
    local data, ip = udp:receivefrom()
    if data and ip and not seen[ip] then
      seen[ip] = true
      hosts[#hosts + 1] = ip
    end
  end
  udp:close()
  return hosts
end

-- Find a specific display, by identity rather than by "something answered".
local function find_by_mac(mac)
  local wanted = normalise_mac(mac)
  if not wanted then return nil end

  local hosts = ssdp_search()
  log.info("SSDP: " .. #hosts .. " responder(s)")
  for _, host in ipairs(hosts) do
    local found, name = tv_identify(host)
    if found == wanted then
      log.info("SSDP: found " .. wanted .. " at " .. host .. " (" .. tostring(name) .. ")")
      return host
    end
  end
  log.warn("SSDP: " .. wanted .. " did not answer")
  return nil
end

-- Device lifecycle handlers
local function device_init(driver, device)
  log.debug(device.id .. ": " .. device.device_network_id .. "> INITIALIZING")
  
  initialized = true
  device:online()
end

local function device_added(driver, device)
  log.info("TV App Launcher device added: " .. device.id)
  
  -- Set initial capability states
  device:emit_event(capabilities.switch.switch.off())
  device:online()
end

local function device_removed(driver, device)
  log.info("TV App Launcher device removed: " .. device.id)
end

-- HTTP request helper
local function nas_base(device)
  local prefs = device.preferences or {}
  local server_url = prefs.serverUrl
  if not server_url or server_url == "" then
    server_url = DEFAULT_SERVER_URL
    log.warn("serverUrl preference is not set - falling back to " .. DEFAULT_SERVER_URL)
  end
  return (server_url:gsub("/+$", ""))
end

local function target_of(device)
  return ((device.preferences or {}).targetDevice) or "s95"
end

-- What the driver needs to go direct: which MAC identifies this display, and
-- which app to open.
--
-- Read from the utility rather than duplicated into preferences, so the .env
-- on the NAS stays the single place these are configured and the two cannot
-- drift apart. Fetched once and remembered; the values only change when the
-- hardware does.
local function display_meta(device)
  local target = target_of(device)
  local mac = device:get_field("mac_" .. target)
  local app_id = device:get_field("app_id")
  if mac and app_id then return mac, app_id end

  local body = {}
  http.TIMEOUT = 10
  local _, code = http.request({
    url = nas_base(device) .. "/displays",
    sink = ltn12.sink.table(body),
  })
  if code ~= 200 then
    log.warn("Could not read /displays from the utility (HTTP " .. tostring(code) ..
             ") - direct launch unavailable until it answers")
    return nil, nil
  end

  local ok, parsed = pcall(json.decode, table.concat(body))
  if not ok or type(parsed) ~= "table" then return nil, nil end

  app_id = parsed.app_id
  local entry = (parsed.displays or {})[target] or {}
  mac = normalise_mac(entry.mac)

  if mac then device:set_field("mac_" .. target, mac, { persist = true }) end
  if app_id then device:set_field("app_id", app_id, { persist = true }) end
  -- The address it reports is as good a starting hint as any.
  if entry.host then device:set_field("host_" .. target, entry.host, { persist = true }) end

  return mac, app_id
end

local function send_http_request(device, action)
  local prefs = device.preferences or {}
  local url = nas_base(device) .. DEFAULT_ENDPOINT
  local target_device = target_of(device)

  log.info("Sending request to: " .. url)
  log.info("Target device: " .. target_device)

  local request_body = json.encode({
    action = action,
    device_id = device.id,
    target_device = target_device,
    timestamp = os.time()
  })

  local headers = {
    ["Content-Type"] = "application/json",
    ["Content-Length"] = tostring(#request_body)
  }

  -- Send the action token only when one is configured. Leave the preference
  -- blank and the driver behaves exactly as before, which is what the utility
  -- expects while its ACTION_TOKEN is empty.
  --
  -- This exists so the endpoint can be locked down later WITHOUT republishing
  -- the driver. Publishing goes through the SmartThings developer API, which
  -- becomes a paid subscription; the driver itself runs on the hub and is
  -- free forever. So the flexibility has to be built in before that door
  -- closes, not when it is first needed.
  local action_token = prefs.actionToken
  if action_token and action_token ~= "" then
    headers["Authorization"] = "Bearer " .. action_token
    log.info("Sending action token")
  end

  local response_body = {}

  http.TIMEOUT = REQUEST_TIMEOUT_SECONDS

  local res, code, response_headers = http.request({
    url = url,
    method = "POST",
    headers = headers,
    source = ltn12.source.string(request_body),
    sink = ltn12.sink.table(response_body)
  })
  
  if code == 200 then
    log.info("Request successful: " .. code)
    -- The utility rediscovers a moved display by MAC and reports where it
    -- actually found it. Keep that: it is how the direct path heals when SSDP
    -- has not managed to.
    local raw = table.concat(response_body)
    local ok, parsed = pcall(json.decode, raw)
    if ok and type(parsed) == "table" and type(parsed.details) == "table" and parsed.details.host then
      device:set_field("host_" .. target_device, parsed.details.host, { persist = true })
      log.info("Learned " .. target_device .. " is at " .. parsed.details.host)
    end
    return true, raw
  elseif code == 401 or code == 403 then
    -- Almost always the action token: either set here and not on the utility,
    -- or set there and left blank here. Say so rather than printing a bare
    -- status, because this is read off the hub's driver log.
    log.error("Request rejected (HTTP " .. tostring(code) ..
              ") - check the Action token preference matches ACTION_TOKEN on the server")
    return false, "HTTP " .. tostring(code)
  else
    log.error("Request failed with code: " .. tostring(code))
    return false, "HTTP " .. tostring(code)
  end
end

-- Open the app, trying the shortest path that can work.
--
--   1. the address we last saw this display at, straight to the set
--   2. SSDP, if that address has gone stale, then straight to the set
--   3. the utility on the NAS, which scans the subnet by MAC
--
-- Each tier exists because the one before it can fail in a way this network
-- actually produces. Addresses drift here - both sets moved twice in a
-- fortnight - so 1 goes stale regularly. SSDP found both sets when probed, but
-- only answers for a display that is powered on, and has never been run from
-- the hub's sandbox. 3 is the path that has been in production for weeks, so
-- it stays as the floor: if the new code cannot do it, the old code still can.
local function launch(device)
  local target = target_of(device)
  local mac, app_id = display_meta(device)

  if app_id then
    local host = device:get_field("host_" .. target)
    if host then
      log.info("Trying " .. target .. " directly at " .. host)
      local ok = tv_launch(host, app_id)
      if ok then
        log.info("Launched on " .. host .. " (direct)")
        return true, "direct"
      end
      log.info("No answer at " .. host .. " - it has probably moved")
    end

    if mac then
      local found = find_by_mac(mac)
      if found then
        local ok = tv_launch(found, app_id)
        if ok then
          device:set_field("host_" .. target, found, { persist = true })
          log.info("Launched on " .. found .. " (found by SSDP)")
          return true, "ssdp"
        end
        log.warn("Found " .. mac .. " at " .. found .. " but the launch failed")
      end
    end
  end

  log.info("Falling back to the utility")
  local ok, response = send_http_request(device, "launch")
  return ok, ok and "utility" or response
end

-- Capability handlers
local function handle_switch_on(driver, device, command)
  log.info("Switch ON command received")

  local success, response = launch(device)

  if success then
    log.info("Launch path: " .. tostring(response))
    device:emit_event(capabilities.switch.switch.on())
    log.info("TV app launch request sent successfully")
  else
    log.error("Failed to send TV app launch request: " .. tostring(response))
    device:emit_event(capabilities.switch.switch.off())
  end
  
  -- Auto-turn off after 2 seconds (momentary switch behavior)
  device.thread:call_with_delay(2, function()
    device:emit_event(capabilities.switch.switch.off())
  end)
end

local function handle_switch_off(driver, device, command)
  log.info("Switch OFF command received")
  device:emit_event(capabilities.switch.switch.off())
end

local function handle_refresh(driver, device, command)
  log.info("Refresh command received")
  device:emit_event(capabilities.switch.switch.off())
end

-- Driver configuration
local tv_app_launcher_driver = Driver("tv-app-launcher", {
  discovery = function(driver, opts, should_continue)
    
    if not initialized then
    
      log.info("Creating TV App Launcher device")
      
      -- Create device during discovery scan
      local device_dni = "tvapplauncher_" .. socket.gettime()
      local metadata = {
        type = "LAN",
        device_network_id = device_dni,
        label = "TV App Launcher",
        profile = "tv-app-launcher-profile",
        manufacturer = "SmartThings Community",
        model = "TVAPPLAUNCHERV1",
        vendor_provided_label = "TV App Launcher"
      }

      log.debug("Creating device with DNI: " .. device_dni)
      
      assert(driver:try_create_device(metadata), "failed to create TV App Launcher device")
      
      log.debug("Device creation completed")
    
    else
      log.info("TV App Launcher device already created")
    end
    
  end,
  lifecycle_handlers = {
    init = device_init,
    added = device_added,
    removed = device_removed
  },
  capability_handlers = {
    [capabilities.switch.ID] = {
      [capabilities.switch.commands.on.NAME] = handle_switch_on,
      [capabilities.switch.commands.off.NAME] = handle_switch_off
    },
    [capabilities.refresh.ID] = {
      [capabilities.refresh.commands.refresh.NAME] = handle_refresh
    }
  }
})

-- Exposed for test/launch_test.lua, which exercises the tier ordering offline.
-- Iterating on the hub costs a package, an assign, an install and a sync, so
-- the logic that decides which path to take is worth checking before any of
-- that. Unused at runtime.
tv_app_launcher_driver.__test = {
  normalise_mac = normalise_mac,
  find_by_mac = find_by_mac,
  launch = launch,
}

-- Start the driver
log.info("TV App Launcher Edge Driver v1.2 Started")

tv_app_launcher_driver:run()

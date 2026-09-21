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
local function send_http_request(device, action)
  local prefs = device.preferences or {}
  local server_url = prefs.serverUrl
  if not server_url or server_url == "" then
    server_url = DEFAULT_SERVER_URL
    log.warn("serverUrl preference is not set - falling back to " .. DEFAULT_SERVER_URL)
  end
  local endpoint = DEFAULT_ENDPOINT
  local url = server_url .. endpoint

  -- Get target device from preferences
  local target_device = prefs.targetDevice or "s95"

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
    return true, table.concat(response_body)
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

-- Capability handlers
local function handle_switch_on(driver, device, command)
  log.info("Switch ON command received")
  
  local success, response = send_http_request(device, "launch")
  
  if success then
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

-- Start the driver
log.info("TV App Launcher Edge Driver v1.1 Started")

tv_app_launcher_driver:run()

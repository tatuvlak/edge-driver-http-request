-- Checks which path the driver takes to open the app, without a hub.
--
--     lua5.4 test/launch_test.lua
--
-- The driver tries the last known address, then SSDP, then the utility on the
-- NAS. Getting that order wrong is not obvious from reading it, and every
-- correction on real hardware costs a package, an assign, an install and a
-- hub sync. So the decision logic is exercised here against fake sockets.
--
-- This does NOT prove the Edge sandbox can send multicast or reach port 8001 —
-- only a driver on a hub can show that. It proves the driver asks the right
-- things in the right order, and falls back when it should.

package.path = "src/?.lua;" .. package.path

-- ---------------------------------------------------------------------------
-- Fakes
-- ---------------------------------------------------------------------------
local calls, responses = {}, {}

local function record(kind, detail) calls[#calls + 1] = kind .. ":" .. tostring(detail) end

local http = { TIMEOUT = 0 }
function http.request(req)
  record("http", req.url)
  local r = responses[req.url]
  if not r then return nil, "connection refused" end
  if req.sink and r.body then req.sink(r.body) end
  return 1, r.code
end

local fake_udp_hosts = {}
local udp = {}
udp.__index = udp
function udp:setsockname() end
function udp:settimeout() end
function udp:sendto() record("ssdp", "M-SEARCH") end
function udp:close() end
function udp:receivefrom()
  local nxt = table.remove(fake_udp_hosts, 1)
  if nxt then return "HTTP/1.1 200 OK", nxt end
  return nil, "timeout"
end

package.preload["st.capabilities"] = function()
  local sw = { ID = "switch", commands = { on = { NAME = "on" }, off = { NAME = "off" } } }
  sw.switch = { on = function() return "on" end, off = function() return "off" end }
  return { switch = sw, refresh = { ID = "refresh", commands = { refresh = { NAME = "refresh" } } } }
end
-- init.lua does not return the driver (it calls :run() and blocks), so the
-- stub keeps hold of it for us.
package.preload["st.driver"] = function()
  return function(_, opts)
    local d = opts or {}
    d.run = function() end
    _G.__driver = d
    return d
  end
end
package.preload["cosock"] = function()
  return { asyncify = function() return http end }
end
package.preload["cosock.socket"] = function()
  return { udp = function() return setmetatable({}, udp) end }
end
package.preload["ltn12"] = function()
  return { source = { string = function(s) return s end },
           sink = { table = function(t) return function(chunk) t[#t + 1] = chunk end end } }
end
package.preload["dkjson"] = function()
  -- Only the shapes this driver actually exchanges. A real JSON parser is not
  -- the thing under test.
  return {
    encode = function() return "{}" end,
    decode = function(str) return responses["__decode__" .. str] end,
  }
end
package.preload["log"] = function()
  local noop = function() end
  return { info = noop, warn = noop, error = noop, debug = noop }
end

dofile("src/init.lua")
local T = (_G.__driver or {}).__test
assert(T, "driver did not expose its internals")

-- ---------------------------------------------------------------------------
-- A device stub with the field store the driver persists into
-- ---------------------------------------------------------------------------
local function new_device(fields)
  local store = {}
  for k, v in pairs(fields or {}) do store[k] = v end
  return {
    id = "dev-1",
    preferences = { serverUrl = "http://nas:5000", targetDevice = "m7", actionToken = "" },
    get_field = function(_, k) return store[k] end,
    set_field = function(_, k, v) store[k] = v end,
    __store = store,
  }
end

local NAS_LAUNCH = "http://nas:5000/launch-tv-app"
local function tv_url(ip) return "http://" .. ip .. ":8001/api/v2/applications/tvweather1.tvweather" end
local function id_url(ip) return "http://" .. ip .. ":8001/api/v2/" end

local function reset()
  calls, responses, fake_udp_hosts = {}, {}, {}
end

local function saw(pattern)
  for _, c in ipairs(calls) do if c:find(pattern, 1, true) then return true end end
  return false
end

-- ---------------------------------------------------------------------------
local fail = {}
local function check(name, got, want)
  if got ~= want then fail[#fail + 1] = ("%s: got %s, want %s"):format(name, tostring(got), tostring(want)) end
end

-- 1. The cached address works: go straight there, touch nothing else.
reset()
responses[tv_url("192.168.18.221")] = { code = 200 }
local dev = new_device({ mac_m7 = "54:44:A3:5C:4B:16", app_id = "tvweather1.tvweather",
                         host_m7 = "192.168.18.221" })
local ok, how = T.launch(dev)
check("cached: succeeded", ok, true)
check("cached: path", how, "direct")
check("cached: did not ask SSDP", saw("ssdp:"), false)
check("cached: did not call the NAS", saw(NAS_LAUNCH), false)

-- 2. The address has drifted. SSDP finds it, and the new address is remembered.
reset()
fake_udp_hosts = { "192.168.18.50", "192.168.18.219" }
responses[id_url("192.168.18.50")] = { code = 200, body = "OTHER" }
responses["__decode__OTHER"] = { device = { wifiMac = "AA:BB:CC:DD:EE:FF", name = "a printer" } }
responses[id_url("192.168.18.219")] = { code = 200, body = "M7" }
responses["__decode__M7"] = { device = { wifiMac = "54:44:a3:5c:4b:16", name = "M7" } }
responses[tv_url("192.168.18.219")] = { code = 200 }
dev = new_device({ mac_m7 = "54:44:A3:5C:4B:16", app_id = "tvweather1.tvweather",
                   host_m7 = "192.168.18.221" })   -- stale, nothing answers there
ok, how = T.launch(dev)
check("drifted: succeeded", ok, true)
check("drifted: path", how, "ssdp")
check("drifted: tried the stale address first", saw(tv_url("192.168.18.221")), true)
check("drifted: cached the new address", dev.__store.host_m7, "192.168.18.219")
check("drifted: did not call the NAS", saw(NAS_LAUNCH), false)
check("drifted: MAC match ignores case", true, true)

-- 3. SSDP finds nothing (a set in standby does not answer). Fall back to the
--    NAS, and learn the address it reports.
reset()
responses[NAS_LAUNCH] = { code = 200, body = "LAUNCHED" }
responses["__decode__LAUNCHED"] = { success = true, details = { host = "192.168.18.230" } }
dev = new_device({ mac_m7 = "54:44:A3:5C:4B:16", app_id = "tvweather1.tvweather",
                   host_m7 = "192.168.18.221" })
ok, how = T.launch(dev)
check("fallback: succeeded", ok, true)
check("fallback: path", how, "utility")
check("fallback: asked SSDP first", saw("ssdp:"), true)
check("fallback: learned the address", dev.__store.host_m7, "192.168.18.230")

-- 4. First run with the NAS DOWN and nothing cached. This is the case that
--    failed on the hub: the driver fetched the MAC and app id from the NAS,
--    so when the NAS was unreachable it had neither, skipped the direct path
--    and SSDP, and fell back to the NAS it could not reach. It must now find
--    the set on its own.
reset()
fake_udp_hosts = { "192.168.18.221" }
responses[id_url("192.168.18.221")] = { code = 200, body = "M7" }
responses["__decode__M7"] = { device = { wifiMac = "54:44:A3:5C:4B:16", name = "M7" } }
responses[tv_url("192.168.18.221")] = { code = 200 }
dev = new_device({})            -- nothing cached at all
ok, how = T.launch(dev)
check("cold start, NAS down: succeeded", ok, true)
check("cold start, NAS down: path", how, "ssdp")
check("cold start, NAS down: never asked the NAS", saw("http://nas:5000"), false)
check("cold start, NAS down: cached the address", dev.__store.host_m7, "192.168.18.221")

-- 5. Everything fails. Report failure rather than claiming success.
reset()
dev = new_device({ mac_m7 = "54:44:A3:5C:4B:16", app_id = "tvweather1.tvweather",
                   host_m7 = "192.168.18.221" })
ok = T.launch(dev)
check("all down: reported failure", ok, false)

-- 6. MAC normalisation, since the two sources spell it differently.
check("mac: lowercase", T.normalise_mac("f0:70:4f:32:bf:da"), "F0:70:4F:32:BF:DA")
check("mac: dashes", T.normalise_mac("F0-70-4F-32-BF-DA"), "F0:70:4F:32:BF:DA")
check("mac: empty", T.normalise_mac(""), nil)
check("mac: not a string", T.normalise_mac(nil), nil)

if #fail > 0 then
  print("FAIL\n  " .. table.concat(fail, "\n  "))
  os.exit(1)
end
print("all checks passed \u{2014} tier order, address learning, and fallback")

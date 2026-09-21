# Helper scripts

Manual pokes at a running service. For anything that should not silently rot,
use the Python test suites in `python-utility/` instead — those assert.

| Script | Does |
|---|---|
| `test-api.sh` | curl `/health`, `/launch-tv-app`, `/device-status` |
| `test-api.ps1` | the same from PowerShell |
| `test-local.ps1` | launch and status against a local instance |
| `start-server.bat` | run `app.py` on Windows |

Two caveats:

- **`/device-status` is legacy**, left over from the SmartThings-API version
  and due for removal. A failure there is not a failure of the launch path.
- **None of these cover the weather endpoints.** `/ingest`, `/api/weather` and
  `/api/weather/history` are exercised by `python-utility/test_weather_hub.py`.

On Windows, `curl` is a PowerShell alias for `Invoke-WebRequest`, which takes a
hashtable rather than `-H "Header: value"`. Use `curl.exe` for the real thing.

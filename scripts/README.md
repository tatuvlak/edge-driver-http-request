# Helper Scripts

This directory contains helper scripts for testing and development.

## test-api.sh

Test the Python utility manually:

```bash
#!/bin/bash

# Test health endpoint
echo "Testing health endpoint..."
curl http://localhost:5000/health
echo -e "\n"

# Test config endpoint
echo "Testing config endpoint..."
curl http://localhost:5000/config
echo -e "\n"

# Test launch endpoint
echo "Testing launch TV app..."
curl -X POST http://localhost:5000/launch-tv-app \
  -H "Content-Type: application/json" \
  -d '{"action": "launch", "device_id": "test"}'
echo -e "\n"

# Test device status
echo "Testing device status..."
curl http://localhost:5000/device-status
echo -e "\n"
```

## test-api.ps1

PowerShell version for Windows:

```powershell
# Test health endpoint
Write-Host "Testing health endpoint..." -ForegroundColor Green
Invoke-RestMethod -Uri "http://localhost:5000/health" | ConvertTo-Json

# Test config endpoint
Write-Host "`nTesting config endpoint..." -ForegroundColor Green
Invoke-RestMethod -Uri "http://localhost:5000/config" | ConvertTo-Json

# Test launch endpoint
Write-Host "`nTesting launch TV app..." -ForegroundColor Green
$body = @{
    action = "launch"
    device_id = "test"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:5000/launch-tv-app" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body | ConvertTo-Json

# Test device status
Write-Host "`nTesting device status..." -ForegroundColor Green
Invoke-RestMethod -Uri "http://localhost:5000/device-status" | ConvertTo-Json
```

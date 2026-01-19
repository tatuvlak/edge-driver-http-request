# Simple API Test Script

$BaseUrl = "http://localhost:5000"

Write-Host ""
Write-Host "======================================"
Write-Host "   TV App Launcher API Tests"
Write-Host "======================================"
Write-Host ""

# Test 1: Health Check
Write-Host "[1/4] Testing health endpoint..." -ForegroundColor Cyan
try {
    $health = Invoke-RestMethod -Uri "$BaseUrl/health"
    Write-Host "  Success!" -ForegroundColor Green
    $health | ConvertTo-Json
} catch {
    Write-Host "  Failed: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Test 2: Configuration
Write-Host "[2/4] Testing config endpoint..." -ForegroundColor Cyan
try {
    $config = Invoke-RestMethod -Uri "$BaseUrl/config"
    Write-Host "  Success!" -ForegroundColor Green
    $config | ConvertTo-Json
} catch {
    Write-Host "  Failed: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Test 3: Launch TV App
Write-Host "[3/4] Testing launch TV app endpoint..." -ForegroundColor Cyan
Write-Host "  WARNING: This will turn on your TV and launch the app!" -ForegroundColor Yellow
$response = Read-Host "  Press Enter to continue or Ctrl+C to skip"

try {
    $body = @{
        action = "launch"
        device_id = "test"
        timestamp = [int][double]::Parse((Get-Date -UFormat %s))
    } | ConvertTo-Json

    $result = Invoke-RestMethod -Uri "$BaseUrl/launch-tv-app" -Method Post -ContentType "application/json" -Body $body
    Write-Host "  Success!" -ForegroundColor Green
    $result | ConvertTo-Json
} catch {
    Write-Host "  Failed: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.ErrorDetails) {
        Write-Host "  Details: $($_.ErrorDetails.Message)" -ForegroundColor Yellow
    }
}
Write-Host ""

# Test 4: Device Status
Write-Host "[4/4] Testing device status endpoint..." -ForegroundColor Cyan
try {
    $status = Invoke-RestMethod -Uri "$BaseUrl/device-status"
    Write-Host "  Success!" -ForegroundColor Green
    $status | ConvertTo-Json -Depth 5
} catch {
    Write-Host "  Failed: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

Write-Host "======================================"
Write-Host "   Tests Complete"
Write-Host "======================================"
Write-Host ""

# TV App Launcher API Test Script
# PowerShell version for Windows

$BaseUrl = "http://localhost:5000"

function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Url,
        [string]$Method = "GET",
        [object]$Body = $null
    )
    
    Write-Host "`n=== Testing: $Name ===" -ForegroundColor Cyan
    
    try {
        $params = @{
            Uri = $Url
            Method = $Method
            ContentType = "application/json"
        }
        
        if ($Body) {
            $params.Body = ($Body | ConvertTo-Json)
        }
        
        $response = Invoke-RestMethod @params
        Write-Host "✓ Success" -ForegroundColor Green
        $response | ConvertTo-Json -Depth 5 | Write-Host
        return $true
    }
    catch {
        Write-Host "✗ Failed" -ForegroundColor Red
        Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Yellow
        
        if ($_.Exception.Response) {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $responseBody = $reader.ReadToEnd()
            Write-Host "Response: $responseBody" -ForegroundColor Yellow
        }
        return $false
    }
}

Write-Host "`n======================================" -ForegroundColor Yellow
Write-Host "   TV App Launcher API Tests" -ForegroundColor Yellow
Write-Host "======================================`n" -ForegroundColor Yellow

# Test 1: Health Check
Test-Endpoint -Name "Health Check" -Url "$BaseUrl/health"

# Test 2: Configuration
Test-Endpoint -Name "Configuration" -Url "$BaseUrl/config"

# Test 3: Launch TV App
$launchBody = @{
    action = "launch"
    device_id = "test"
    timestamp = [int][double]::Parse((Get-Date -UFormat %s))
}
Test-Endpoint -Name "Launch TV App" -Url "$BaseUrl/launch-tv-app" -Method "POST" -Body $launchBody

# Test 4: Device Status
Test-Endpoint -Name "Device Status" -Url "$BaseUrl/device-status"

Write-Host "`n======================================" -ForegroundColor Yellow
Write-Host "   Tests Complete" -ForegroundColor Yellow
Write-Host "======================================`n" -ForegroundColor Yellow

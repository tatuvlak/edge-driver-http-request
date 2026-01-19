# Extract Credentials from Existing Projects
# Helps populate the .env file with your actual values

Write-Host ""
Write-Host "======================================" -ForegroundColor Yellow
Write-Host "   Credential Extraction Helper" -ForegroundColor Yellow
Write-Host "======================================" -ForegroundColor Yellow
Write-Host ""

$scriptPath = Split-Path -Parent $PSScriptRoot
$pythonScriptPath = "C:\Users\barte\Documents\Projekty\python scripts\tv-app-launch.py"
$configJsPath = "C:\Users\barte\Documents\Projekty\samsung-tv-weather-app\tizen-app\config.js"

Write-Host "Extracting credentials from existing projects..." -ForegroundColor Cyan
Write-Host ""

# Extract from tv-app-launch.py
if (Test-Path $pythonScriptPath) {
    Write-Host "[1] From tv-app-launch.py:" -ForegroundColor Green
    $pythonContent = Get-Content $pythonScriptPath -Raw
    
    if ($pythonContent -match 'PAT_TOKEN\s*=\s*"([^"]+)"') {
        Write-Host "    PAT Token: $($matches[1])" -ForegroundColor White
        $patToken = $matches[1]
    }
    
    if ($pythonContent -match 'DEVICE_ID\s*=\s*"([^"]+)"') {
        Write-Host "    TV Device ID: $($matches[1])" -ForegroundColor White
        $deviceId = $matches[1]
    }
    
    if ($pythonContent -match 'APP_ID\s*=\s*"([^"]+)"') {
        Write-Host "    TV App ID: $($matches[1])" -ForegroundColor White
        $appId = $matches[1]
    }
} else {
    Write-Host "[1] tv-app-launch.py not found" -ForegroundColor Yellow
}

Write-Host ""

# Extract from config.js
if (Test-Path $configJsPath) {
    Write-Host "[2] From samsung-tv-weather-app config.js:" -ForegroundColor Green
    $configContent = Get-Content $configJsPath -Raw
    
    if ($configContent -match 'clientId:\s*"([^"]+)"') {
        Write-Host "    OAuth Client ID: $($matches[1])" -ForegroundColor White
        $clientId = $matches[1]
    }
    
    if ($configContent -match 'clientSecret:\s*"([^"]+)"') {
        Write-Host "    OAuth Client Secret: $($matches[1])" -ForegroundColor White
        $clientSecret = $matches[1]
    }
    
    if ($configContent -match 'pat:\s*"([^"]+)"') {
        Write-Host "    PAT (from config.js): $($matches[1])" -ForegroundColor White
        if (-not $patToken) {
            $patToken = $matches[1]
        }
    }
} else {
    Write-Host "[2] config.js not found" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Yellow
Write-Host "   Generate .env file" -ForegroundColor Yellow
Write-Host "======================================" -ForegroundColor Yellow
Write-Host ""

# Create .env file content
$envContent = @"
# Environment configuration for TV App Launcher
# Auto-generated from existing projects

# SmartThings Personal Access Token (for testing)
SMARTTHINGS_PAT=$patToken

# SmartThings OAuth (for production)
ST_CLIENT_ID=$clientId
ST_CLIENT_SECRET=$clientSecret
ST_REFRESH_TOKEN=

# TV Configuration
TV_DEVICE_ID=$deviceId
TV_APP_ID=$appId

# Server Configuration
HOST=0.0.0.0
PORT=5000
"@

$envPath = Join-Path $scriptPath "python-utility\.env"

Write-Host "Saving to: $envPath" -ForegroundColor Cyan

$envContent | Out-File -FilePath $envPath -Encoding UTF8

Write-Host ""
Write-Host "Done! .env file created successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Review the file and add your ST_REFRESH_TOKEN if using OAuth." -ForegroundColor Yellow
Write-Host "To get a refresh token, you need to complete the OAuth flow first." -ForegroundColor Yellow

Write-Host ""
Write-Host "======================================" -ForegroundColor Yellow
Write-Host "   Next Steps" -ForegroundColor Yellow
Write-Host "======================================" -ForegroundColor Yellow
Write-Host ""

Write-Host "1. Review the .env file: python-utility\.env" -ForegroundColor White
Write-Host "2. Test locally (optional):" -ForegroundColor White
Write-Host "   cd python-utility" -ForegroundColor Gray
Write-Host "   pip install -r requirements.txt" -ForegroundColor Gray
Write-Host "   python app.py" -ForegroundColor Gray
Write-Host "3. Deploy to QNAP with Docker" -ForegroundColor White
Write-Host ""




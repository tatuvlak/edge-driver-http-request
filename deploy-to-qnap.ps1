# Deploy TV App Launcher to QNAP via SSH
# This script uploads files and builds the image directly on QNAP

param(
    [Parameter(Mandatory=$true)]
    [string]$QnapIP,
    
    [Parameter(Mandatory=$false)]
    [string]$Username = "bartek"
)

Write-Host "`n=== Deploying TV App Launcher to QNAP ===" -ForegroundColor Cyan
Write-Host "QNAP IP: $QnapIP" -ForegroundColor Yellow
Write-Host "Username: $Username" -ForegroundColor Yellow

# Step 1: Create directory on QNAP
Write-Host "`n[1/6] Creating directory on QNAP..." -ForegroundColor Green
ssh ${Username}@${QnapIP} "mkdir -p /share/Container/tv-app-launcher"

# Step 2: Upload files
Write-Host "`n[2/6] Uploading files..." -ForegroundColor Green
$sourceDir = Join-Path $PSScriptRoot "python-utility"

Write-Host "  - Uploading app.py"
scp "${sourceDir}\app.py" ${Username}@${QnapIP}:/share/Container/tv-app-launcher/

Write-Host "  - Uploading requirements.txt"
scp "${sourceDir}\requirements.txt" ${Username}@${QnapIP}:/share/Container/tv-app-launcher/

Write-Host "  - Uploading Dockerfile"
scp "${sourceDir}\Dockerfile" ${Username}@${QnapIP}:/share/Container/tv-app-launcher/

Write-Host "  - Uploading .env"
scp "${sourceDir}\.env" ${Username}@${QnapIP}:/share/Container/tv-app-launcher/

# Step 3: Build image on QNAP
Write-Host "`n[3/6] Building Docker image on QNAP..." -ForegroundColor Green
Write-Host "  (This will take 2-5 minutes on first build)" -ForegroundColor Yellow
ssh ${Username}@${QnapIP} "cd /share/Container/tv-app-launcher && docker build -t tv-app-launcher:latest ."

# Step 4: Stop old container if exists
Write-Host "`n[4/6] Stopping old container (if exists)..." -ForegroundColor Green
ssh ${Username}@${QnapIP} "docker stop tv-app-launcher 2>/dev/null || true"
ssh ${Username}@${QnapIP} "docker rm tv-app-launcher 2>/dev/null || true"

# Step 5: Create and start container
Write-Host "`n[5/6] Creating and starting container..." -ForegroundColor Green
ssh ${Username}@${QnapIP} @"
docker run -d \
  --name tv-app-launcher \
  --restart unless-stopped \
  -p 5000:5000 \
  --env-file /share/Container/tv-app-launcher/.env \
  tv-app-launcher:latest
"@

# Step 6: Verify container is running
Write-Host "`n[6/6] Verifying container status..." -ForegroundColor Green
Start-Sleep -Seconds 3

$containerStatus = ssh ${Username}@${QnapIP} "docker ps --filter name=tv-app-launcher --format '{{.Status}}'"

if ($containerStatus) {
    Write-Host "`n✅ Container is running: $containerStatus" -ForegroundColor Green
    
    Write-Host "`n=== Testing Service ===" -ForegroundColor Cyan
    Start-Sleep -Seconds 2
    
    try {
        $health = Invoke-RestMethod -Uri "http://${QnapIP}:5000/health" -TimeoutSec 5
        Write-Host "✅ Health check passed:" -ForegroundColor Green
        Write-Host "   Status: $($health.status)" -ForegroundColor White
        Write-Host "   Version: $($health.version)" -ForegroundColor White
        
        Write-Host "`n=== Deployment Successful! ===" -ForegroundColor Green
        Write-Host "`nNext steps:" -ForegroundColor Cyan
        Write-Host "1. Update SmartThings Edge driver Server URL to: http://${QnapIP}:5000" -ForegroundColor Yellow
        Write-Host "2. Test the TV App Launcher switch in SmartThings app" -ForegroundColor Yellow
        Write-Host "3. Your TV should turn on and launch the weather app!" -ForegroundColor Yellow
        
    } catch {
        Write-Host "⚠️  Container running but health check failed" -ForegroundColor Yellow
        Write-Host "   Check logs: ssh ${Username}@${QnapIP} 'docker logs tv-app-launcher'" -ForegroundColor Gray
    }
} else {
    Write-Host "`n❌ Container failed to start" -ForegroundColor Red
    Write-Host "   Check logs: ssh ${Username}@${QnapIP} 'docker logs tv-app-launcher'" -ForegroundColor Gray
}

Write-Host ""

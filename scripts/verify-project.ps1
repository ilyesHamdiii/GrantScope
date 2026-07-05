$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
    throw ".env is missing. Create it from .env.example before running verification."
}

Write-Host ""
Write-Host "Starting GrantScope containers..." -ForegroundColor Cyan
docker compose up --build -d

$ApiReady = $false
$FrontendReady = $false

Write-Host ""
Write-Host "Waiting for API and frontend..." -ForegroundColor Cyan

for ($Attempt = 1; $Attempt -le 60; $Attempt++) {
    Start-Sleep -Seconds 2

    if (-not $ApiReady) {
        try {
            $Health = Invoke-RestMethod `
                -Uri "http://localhost:8000/health" `
                -TimeoutSec 5

            if ($Health.status -eq "healthy") {
                $ApiReady = $true
            }
        }
        catch {
        }
    }

    if (-not $FrontendReady) {
        try {
            $FrontendResponse = Invoke-WebRequest `
                -Uri "http://localhost:5173" `
                -UseBasicParsing `
                -TimeoutSec 5

            if ($FrontendResponse.Content -match "GrantScope") {
                $FrontendReady = $true
            }
        }
        catch {
        }
    }

    if ($ApiReady -and $FrontendReady) {
        break
    }

    Write-Host "Waiting for services... ($Attempt/60)" -ForegroundColor DarkYellow
}

if (-not $ApiReady -or -not $FrontendReady) {
    Write-Host ""
    Write-Host "Services failed to start. Recent logs:" -ForegroundColor Red
    docker compose logs --tail=250
    exit 1
}

Write-Host ""
Write-Host "Running backend test suite..." -ForegroundColor Cyan
docker compose exec -T -w /app api python -m pytest -q /app/tests

if ($LASTEXITCODE -ne 0) {
    throw "Backend tests failed."
}

Write-Host ""
Write-Host "Building React frontend..." -ForegroundColor Cyan
docker compose exec -T frontend npm run build

if ($LASTEXITCODE -ne 0) {
    throw "React production build failed."
}

Write-Host ""
Write-Host "GrantScope verification completed successfully." -ForegroundColor Green
Write-Host "Workbench: http://localhost:5173"
Write-Host "API docs:  http://localhost:8000/docs"
Write-Host ""

docker compose ps
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$ErrorActionPreference = "Stop"

$DemoZip = Join-Path $ProjectRoot "sample-data\demo-tenant.zip"

if (-not (Test-Path $DemoZip)) {
    throw "Demo bundle not found: $DemoZip"
}

try {
    $Health = Invoke-RestMethod `
        -Uri "http://localhost:8000/health" `
        -TimeoutSec 5

    if ($Health.status -ne "healthy") {
        throw "GrantScope API is not healthy."
    }
}
catch {
    throw "GrantScope API is unavailable. Start containers first with: docker compose up -d"
}

Write-Host ""
Write-Host "Importing GrantScope demonstration tenant..." -ForegroundColor Cyan

$UploadResponse = & curl.exe -sS -X POST `
    "http://localhost:8000/api/v1/imports/bundle" `
    -F "file=@$DemoZip;type=application/zip"

if ($LASTEXITCODE -ne 0) {
    throw "Demo evidence bundle upload failed."
}

$ImportJson = $UploadResponse | ConvertFrom-Json
$RunId = $ImportJson.import_run.id

Write-Host "Import Run ID: $RunId" -ForegroundColor Green

Write-Host ""
Write-Host "Running detection and correlation..." -ForegroundColor Cyan

$Analysis = Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/import-runs/$RunId/analyze" `
    -Method Post

Write-Host "Findings created: $($Analysis.finding_count)" -ForegroundColor Green

Write-Host ""
Write-Host "Generating analyst case packets..." -ForegroundColor Cyan

$Cases = Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/import-runs/$RunId/cases/generate" `
    -Method Post

Write-Host ""
Write-Host "Generated cases:" -ForegroundColor Cyan

$Cases.cases |
    Select-Object severity, confidence, finding_count, evidence_count, title, id |
    Format-Table -AutoSize

$CriticalCase = $Cases.cases |
    Where-Object { $_.severity -eq "critical" } |
    Select-Object -First 1

if ($CriticalCase) {
    Write-Host ""
    Write-Host "Critical case:" -ForegroundColor Green
    Write-Host $CriticalCase.title -ForegroundColor Green
    Write-Host "Case ID: $($CriticalCase.id)" -ForegroundColor Green
    Write-Host "Case API: http://localhost:8000/api/v1/cases/$($CriticalCase.id)" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "Opening GrantScope workbench..." -ForegroundColor Cyan
Start-Process "http://localhost:5173"
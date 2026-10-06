# EcoTwin Backend Starter
# Run this script from the project root: .\start_backend.ps1

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$backendDir = Join-Path $PSScriptRoot "backend"
$envFile = Join-Path $backendDir ".env"

# Read APP_HOST and APP_PORT from backend/.env (fallback to defaults)
$host_val = "127.0.0.1"
$port_val = "8000"
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match "^\s*APP_HOST\s*=\s*(.+)") { $host_val = $matches[1].Trim() }
        if ($line -match "^\s*APP_PORT\s*=\s*(.+)") { $port_val = $matches[1].Trim() }
    }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  EcoTwin Backend Starting..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Python  : $python"
Write-Host "WorkDir : $backendDir"
Write-Host "Address : http://${host_val}:${port_val}"
Write-Host ""

Set-Location $backendDir
& $python -m uvicorn main:app --host $host_val --port $port_val --reload

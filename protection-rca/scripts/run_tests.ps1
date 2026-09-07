# Run Protection RCA backend + frontend tests (Windows PowerShell).
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "==> Backend pytest"
Set-Location (Join-Path $Root "backend")
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$($env:PYTHONPATH);$Root\backend" } else { "$Root\backend" }

$venvActivate = Join-Path (Get-Location) ".venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    . $venvActivate
}

pytest -q @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> Frontend vitest"
Set-Location (Join-Path $Root "frontend")
if (-not (Test-Path "node_modules")) {
    npm install
}
npm test
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> All tests finished"

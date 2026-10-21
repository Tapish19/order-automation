param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) { throw 'Create .venv and install requirements.lock.txt first. See README.md.' }
if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) { throw 'Build the frontend first: cd frontend; npm ci; npm run build. See README.md.' }
Write-Host "NaturaX: http://127.0.0.1:$Port  | API docs: http://127.0.0.1:$Port/docs"
& '.venv/Scripts/python.exe' -m uvicorn backend.app.main:app --host 127.0.0.1 --port $Port

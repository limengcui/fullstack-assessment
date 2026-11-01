$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (!(Test-Path ".venv/Scripts/python.exe")) { throw "Please follow README to install dependencies first." }
Push-Location app/frontend
try { npm run build; if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" } } finally { Pop-Location }
& ./.venv/Scripts/python.exe -m uvicorn app.backend.main:app --host 127.0.0.1 --port 8000

# Yerel kurulum (Windows PowerShell): .\scripts\local\kur.ps1
Set-Location (Join-Path $PSScriptRoot "..\..")
python -m venv .venv
.\.venv\Scripts\pip install -q -e ".[dev]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Write-Host "Kurulum tamam. Baslatmak icin:"
Write-Host '  $env:EVREN_API_KEY="..."   # anahtarini buraya yaz'
Write-Host '  $env:PYTHONPATH="src"; .\.venv\Scripts\uvicorn medrag.api.main:app --host 0.0.0.0 --port 8000'

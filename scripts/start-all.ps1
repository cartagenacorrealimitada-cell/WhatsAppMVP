# Arranque diario: FastAPI (uvicorn) + ngrok con URL fija.
# Uso (desde la raíz del proyecto):
#   .\scripts\start-all.ps1
#
# Abre dos ventanas de PowerShell. Cierra cada una para detener ese proceso.

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "app\main.py"))) {
    Write-Error "Ejecuta desde el repo WhatsAppMVP (no se encontró app\main.py)."
}

$url = if ($env:PUBLIC_BASE_URL) {
    $env:PUBLIC_BASE_URL.TrimEnd("/")
} else {
    "https://backyard-overture-schilling.ngrok-free.dev"
}

Write-Host "Proyecto: $Root"
Write-Host "Uvicorn:  http://127.0.0.1:8000"
Write-Host "Público:  $url"
Write-Host "Webhook:  $url/webhook"
Write-Host ""
Write-Host "Abriendo Terminal A (uvicorn) y Terminal B (ngrok)..."

$uvicornCmd = @"
Set-Location -LiteralPath '$Root'
Write-Host 'Terminal A — uvicorn (Ctrl+C para detener)'
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
"@

$ngrokCmd = @"
Set-Location -LiteralPath '$Root'
Write-Host 'Terminal B — ngrok (Ctrl+C para detener)'
Write-Host 'Meta Callback URL: $url/webhook'
& '$Root\scripts\start-ngrok.ps1'
"@

Start-Process powershell -WorkingDirectory $Root -ArgumentList @(
    "-NoExit",
    "-Command",
    $uvicornCmd
)

Start-Sleep -Seconds 1

Start-Process powershell -WorkingDirectory $Root -ArgumentList @(
    "-NoExit",
    "-Command",
    $ngrokCmd
)

Write-Host "Listo. Prueba de humo: WhatsApp → hola"

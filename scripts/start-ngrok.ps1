# Arranca ngrok con el dominio fijo del proyecto (URL estable para Meta).
# Uso: .\scripts\start-ngrok.ps1

$ErrorActionPreference = "Stop"
$url = if ($env:PUBLIC_BASE_URL) { $env:PUBLIC_BASE_URL.TrimEnd("/") } else { "https://backyard-overture-schilling.ngrok-free.dev" }

Write-Host "ngrok -> http://127.0.0.1:8000  public=$url"
Write-Host "Meta Callback URL: $url/webhook"
ngrok http 8000 --url $url

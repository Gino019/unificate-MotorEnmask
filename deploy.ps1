# SecOps Universal - Script de despliegue con Docker Compose
# Uso: .\deploy.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

function Test-Docker {
    try {
        $null = Get-Command docker -ErrorAction Stop
        docker info *> $null
        return $true
    } catch {
        return $false
    }
}

Write-Host ""
Write-Host "=== SecOps Universal - Deploy ===" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Docker)) {
    Write-Host "ERROR: Docker no esta instalado o no esta en ejecucion." -ForegroundColor Red
    Write-Host ""
    Write-Host "Instala Docker Desktop para Windows:" -ForegroundColor Yellow
    Write-Host "  https://www.docker.com/products/docker-desktop/"
    Write-Host ""
    Write-Host "Tras instalarlo, abre Docker Desktop y vuelve a ejecutar: .\deploy.ps1"
    exit 1
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Archivo .env creado desde .env.example" -ForegroundColor Yellow
    Write-Host "Edita .env antes de produccion." -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "Construyendo imagenes y levantando el stack completo..." -ForegroundColor Green
docker compose up -d --build

Write-Host ""
Write-Host "Esperando healthchecks..." -ForegroundColor Gray
Start-Sleep -Seconds 15
docker compose ps

Write-Host ""
Write-Host "=== Stack listo ===" -ForegroundColor Green
Write-Host "  Panel web:       http://localhost:8000/login"
Write-Host "  API Gateway:     http://localhost:8000"
Write-Host "  Masking Service: http://localhost:8001"
Write-Host "  Monitor Service: http://localhost:8002"
Write-Host "  Neo4j Browser:   http://localhost:7474"
Write-Host ""
Write-Host "Admin por defecto: admin@secops.local / Admin1234!"
Write-Host 'Logs: docker compose logs -f api'
Write-Host ""

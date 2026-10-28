# Demo guiada para la presentación en Windows (Docker Desktop + PowerShell, sin Ubuntu).
# Lanza tools/demo/presentacion.py con el Python instalado y revisa antes que Docker Desktop esté corriendo.
#
# Uso (en la carpeta del repositorio):
#   powershell -ExecutionPolicy Bypass -File scripts\windows\presentacion.ps1 -Preparar   # la víspera: descarga y compila todo
#   powershell -ExecutionPolicy Bypass -File scripts\windows\presentacion.ps1             # la demo, con pausas (Enter)
#   powershell -ExecutionPolicy Bypass -File scripts\windows\presentacion.ps1 -SinPausa -AbrirNavegador
#   powershell -ExecutionPolicy Bypass -File scripts\windows\presentacion.ps1 -Apagar     # al terminar
param([switch]$Preparar, [switch]$SinPausa, [switch]$SinDocker, [switch]$AbrirNavegador, [switch]$Apagar)
. (Join-Path $PSScriptRoot 'comun.ps1')
Set-Location $Raiz
$compose = Comando-Compose

if ($Apagar) { & docker @compose down; exit $LASTEXITCODE }

if (-not (Obtener-Python)) { Write-Host 'Falta Python 3.9 o superior: winget install Python.Python.3.12' -ForegroundColor Red; exit 1 }
if (-not $SinDocker) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-Host 'Falta Docker Desktop: winget install Docker.DockerDesktop' -ForegroundColor Red; exit 1 }
    & docker info --format '{{.ServerVersion}}' *> $null
    if ($LASTEXITCODE -ne 0) { Write-Host "Docker Desktop no está corriendo: ábralo, espere a 'Engine running' y repita." -ForegroundColor Red; exit 1 }
}

if ($Preparar) {
    # Deja todo descargado y compilado para que la demo no dependa de la red ni tarde en la primera ejecución
    Write-Host '> Descargando la imagen del SDK de .NET 10 (compila el código generado)...'
    & docker pull mcr.microsoft.com/dotnet/sdk:10.0; Exigir 'docker pull'
    Write-Host '> Construyendo y levantando el entorno (SQL Server, emulador de ADF, apps)...'
    & docker @compose up -d --build; Exigir 'docker compose up'
    if (-not (Esperar-Salud $ApiUrl 300)) { Write-Host "La API no respondió en $ApiUrl" -ForegroundColor Red; exit 1 }
    Write-Host '> Ensayo completo de la demo, de corrido...'
    Invocar-Python @('tools/demo/presentacion.py', '--sin-pausa')
    Write-Host ''
    Write-Host 'Listo para presentar. El entorno queda arriba; para apagarlo: scripts\windows\presentacion.ps1 -Apagar' -ForegroundColor Green
    exit 0
}

$a = @('tools/demo/presentacion.py')
if ($SinPausa) { $a += '--sin-pausa' }
if ($SinDocker) { $a += '--sin-docker' }
Invocar-Python $a
if ($AbrirNavegador -and -not $SinDocker) {
    Start-Process $ApiUrl
    Start-Process (Join-Path $Raiz 'sistemas/polizas/reingenieria/vb6graph/reporte.html')
}

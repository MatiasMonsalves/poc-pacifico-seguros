# Revisa que este equipo Windows pueda levantar y verificar la fábrica con Docker Desktop (sin Ubuntu).
# Uso: scripts\windows\requisitos.ps1 [-SinDocker]
param([switch]$SinDocker)
. (Join-Path $PSScriptRoot 'comun.ps1')
$ErrorActionPreference = 'Continue'
$script:errores = 0
function Ok($t)    { Write-Host "  [OK]    $t" -ForegroundColor Green }
function Aviso($t) { Write-Host "  [AVISO] $t" -ForegroundColor Yellow }
function Falla($t) { Write-Host "  [FALTA] $t" -ForegroundColor Red; $script:errores++ }

Write-Host 'Requisitos (Windows + Docker Desktop)'

# Un repositorio dentro de C:\Windows (por ejemplo system32, la carpeta inicial de PowerShell como
# administrador) da problemas de permisos y de redirección de archivos
if ($env:windir -and $Raiz.StartsWith($env:windir, [StringComparison]::OrdinalIgnoreCase)) {
    Falla "El repositorio está en $Raiz. Clónelo en una carpeta de usuario, por ejemplo: cd `$HOME; git clone ..."
}

# Los scripts .sh de infra/ corren dentro de contenedores Linux: con saltos de línea CRLF fallan.
# Pasa al clonar la rama main y cambiar de rama: Git no reescribe los archivos que no cambiaron.
# Se reparan solos volviendo a sacarlos de git (el repositorio los guarda en LF).
function ConCrlf { @(Get-ChildItem (Join-Path $Raiz 'infra') -Filter *.sh -File | Where-Object { [IO.File]::ReadAllText($_.FullName).Contains("`r") }) }
$conCrlf = ConCrlf
if ($conCrlf.Count -gt 0 -and (Get-Command git -ErrorAction SilentlyContinue)) {
    foreach ($archivo in $conCrlf) {
        $relativo = $archivo.FullName.Substring($Raiz.Length + 1) -replace '\\', '/'
        Remove-Item $archivo.FullName -Force
        git -C $Raiz checkout -- $relativo 2>$null
    }
    if ((ConCrlf).Count -eq 0) { Ok "Saltos de línea de $($conCrlf.Name -join ', ') reparados a LF" }
    $conCrlf = ConCrlf
} elseif ($conCrlf.Count -eq 0) {
    Ok 'Saltos de línea de los scripts que corren en contenedores (LF)'
}
if ($conCrlf.Count -gt 0) { Falla "Scripts con saltos de línea CRLF ($($conCrlf.Name -join ', ')). Vuelva a clonar con: git clone -b poc/estructura-ingenieria-inversa <url>" }

$py = Obtener-Python
if ($py) { $extra = @(); if ($py.Count -gt 1) { $extra = $py[1..($py.Count - 1)] }; Ok "Python $(& $py[0] @extra -c 'import platform; print(platform.python_version())') ($($py -join ' '))" }
else { Falla 'Python 3.9 o superior. Instálelo con: winget install Python.Python.3.12 (y abra una nueva ventana de PowerShell)' }

if (Get-Command git -ErrorAction SilentlyContinue) { Ok 'Git' } else { Aviso 'Git no está instalado (winget install Git.Git); solo hace falta para clonar y actualizar el repositorio' }
if (Get-Command rea -ErrorAction SilentlyContinue) { Ok 'REA' } else { Aviso 'REA no instalado (opcional): se reutiliza el análisis de binarios guardado. Requiere Node.js 22: winget install OpenJS.NodeJS.LTS y luego npm install -g rea-agents' }

if (-not $SinDocker) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Falla 'Docker Desktop no está instalado (winget install Docker.DockerDesktop)'
    } else {
        $null = docker info 2>$null
        if ($LASTEXITCODE -ne 0) {
            Falla 'Docker Desktop no responde: ábralo y espere a que diga "Engine running"'
        } else {
            Ok "Docker $(docker version --format '{{.Server.Version}}' 2>$null)"
            $null = docker compose version 2>$null
            if ($LASTEXITCODE -eq 0) { Ok "Docker Compose $(docker compose version --short 2>$null)" } else { Falla 'Docker Compose v2 (viene con Docker Desktop: actualícelo)' }
            if ((docker info --format '{{.OSType}}' 2>$null) -ne 'linux') {
                Falla 'Docker Desktop está en modo "Windows containers": cámbielo con el ícono de Docker > "Switch to Linux containers"'
            }
            $memoria = [double](docker info --format '{{.MemTotal}}' 2>$null)
            if ($memoria -lt 3.8GB) { Falla "Docker tiene $([math]::Round($memoria / 1GB, 1)) GB de memoria; SQL Server necesita al menos 4 GB (Settings > Resources, o .wslconfig con memory=8GB)" }
            else { Ok "Memoria para Docker: $([math]::Round($memoria / 1GB)) GB" }

            $contenedores = (docker ps --format '{{.Names}} {{.Ports}}' 2>$null) -join "`n"
            foreach ($par in @(@('SQL_PORT', 1433), @('API_PORT', 8080), @('GEN_PORT', 8081), @('ADF_PORT', 5080))) {
                $puerto = [int](Valor $par[0] $par[1])
                $ocupado = $false
                if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
                    $ocupado = [bool](Get-NetTCPConnection -State Listen -LocalPort $puerto -ErrorAction SilentlyContinue)
                } else {
                    try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', $puerto); $c.Close(); $ocupado = $true } catch { }
                }
                if (-not $ocupado) { Ok "Puerto $puerto libre" }
                elseif ($contenedores -match "poc-pacifico\S*\s.*:$puerto->") { Ok "Puerto $puerto (en uso por este mismo entorno)" }
                else { Falla "El puerto $puerto está ocupado por otro programa. Copie .env.example a .env y cambie $($par[0])" }
            }
        }
    }
    if ($env:CA_BUNDLE -and -not (Test-Path $env:CA_BUNDLE)) { Falla "CA_BUNDLE apunta a un archivo que no existe: $env:CA_BUNDLE" }
    foreach ($url in 'https://mcr.microsoft.com/v2/', 'https://api.nuget.org/v3/index.json') {
        try { $null = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 15 -ErrorAction Stop; Ok "Acceso a $url" }
        catch {
            if ($_.Exception.Response) { Ok "Acceso a $url" }
            elseif ("$($_.Exception.Message)" -match 'SSL|TLS|certific|trust') { Falla "Error de certificado con $url : proxy corporativo. Pida a TI el certificado raíz (.pem) y defina `$env:CA_BUNDLE = 'C:\ruta\cert.pem'" }
            else { Falla "Sin acceso a $url ($($_.Exception.Message))" }
        }
    }
}

if ($script:errores -gt 0) { Write-Host "Faltan $script:errores requisito(s)." -ForegroundColor Red; exit 1 }
Write-Host 'Todo listo.' -ForegroundColor Green
exit 0

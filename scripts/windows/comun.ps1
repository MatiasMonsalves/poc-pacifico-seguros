# Utilidades comunes de los scripts para Windows (Docker Desktop + PowerShell, sin Ubuntu).
# Compatible con Windows PowerShell 5.1 y PowerShell 7.

# 'Continue': en Windows PowerShell 5.1 lo que docker/dotnet/python escriben en stderr (por ejemplo el
# progreso de docker compose) se vuelve error y con 'Stop' cortaría el script. Las fallas se detectan
# por el código de salida (Exigir, Invocar-*), y Llamar usa -ErrorAction Stop explícito.
$ErrorActionPreference = 'Continue'
# Windows PowerShell 5.1 (.NET Framework) puede negociar TLS antiguo: se fuerza TLS 1.2 o superior
if ($PSVersionTable.PSVersion.Major -lt 6) {
    $protocolos = [Net.SecurityProtocolType]::Tls12
    if ([Enum]::GetNames([Net.SecurityProtocolType]) -contains 'Tls13') { $protocolos = $protocolos -bor [Net.SecurityProtocolType]::Tls13 }
    [Net.ServicePointManager]::SecurityProtocol = $protocolos
}
$Raiz = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$env:PYTHONUTF8 = '1'          # las herramientas Python escriben y muestran UTF-8 aunque la consola sea cp1252
$env:PYTHONIOENCODING = 'utf-8'

# Variables de .env (puertos, clave de SQL Server) como en docker compose
$envArchivo = Join-Path $Raiz '.env'
if (Test-Path $envArchivo) {
    foreach ($linea in Get-Content $envArchivo) {
        if ($linea -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { Set-Item -Path "env:$($Matches[1])" -Value $Matches[2].Trim('"') }
    }
}
function Valor($nombre, $porDefecto) { $v = [Environment]::GetEnvironmentVariable($nombre); if ($v) { $v } else { $porDefecto } }
$ApiUrl = "http://localhost:$(Valor 'API_PORT' 8080)"
$GenUrl = "http://localhost:$(Valor 'GEN_PORT' 8081)"
$AdfUrl = "http://localhost:$(Valor 'ADF_PORT' 5080)"

# Python 3.9+: el lanzador "py" de python.org, o "python"/"python3" (se descarta el atajo de Microsoft Store)
function Obtener-Python {
    foreach ($candidato in @(@('py', '-3'), @('python'), @('python3'))) {
        if (-not (Get-Command $candidato[0] -ErrorAction SilentlyContinue)) { continue }
        $extra = @(); if ($candidato.Count -gt 1) { $extra = $candidato[1..($candidato.Count - 1)] }
        $v = & $candidato[0] @extra -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and "$v" -match '^3\.(\d+)$' -and [int]$Matches[1] -ge 9) { return , $candidato }
    }
    return $null
}

function Invocar-Python([string[]]$Argumentos) {
    $py = Obtener-Python
    if (-not $py) { throw 'Python 3.9 o superior no encontrado (winget install Python.Python.3.12)' }
    $extra = @(); if ($py.Count -gt 1) { $extra = $py[1..($py.Count - 1)] }
    & $py[0] @extra @Argumentos
    if ($LASTEXITCODE -ne 0) { throw "Python terminó con código $LASTEXITCODE" }
}

# CLI de .NET 10 dentro del contenedor oficial del SDK (no requiere instalar .NET en Windows)
function Invocar-Dotnet([string]$Carpeta, [string[]]$Argumentos) {
    $trabajo = '/src/' + ($Carpeta -replace '\\', '/')
    $opciones = @('run', '--rm', '-v', "${Raiz}:/src", '-v', 'poc-nuget:/root/.nuget/packages', '-w', $trabajo)
    if ($env:POC_DOCKER_RED) { $opciones += @('--network', $env:POC_DOCKER_RED) }
    if ($env:CA_BUNDLE) {
        $opciones += @('-e', 'HTTPS_PROXY', '-e', 'HTTP_PROXY', '-e', 'NO_PROXY', '-e', 'SSL_CERT_FILE=/ca.crt', '-v', "$($env:CA_BUNDLE):/ca.crt:ro")
    }
    & docker @opciones 'mcr.microsoft.com/dotnet/sdk:10.0' dotnet @Argumentos
    if ($LASTEXITCODE -ne 0) { throw "dotnet $($Argumentos -join ' ') terminó con código $LASTEXITCODE" }
}

function Exigir([string]$que) { if ($LASTEXITCODE -ne 0) { throw "$que terminó con código $LASTEXITCODE" } }

function Comando-Compose {
    $archivos = @('compose', '-f', (Join-Path $Raiz 'docker-compose.yml'))
    if ($env:CA_BUNDLE) { $archivos += @('-f', (Join-Path $Raiz 'docker-compose.proxy.yml')) }
    return , $archivos
}

# HTTP con el código de estado aunque sea 4xx/5xx (Invoke-RestMethod lanza excepción en esos casos)
function Llamar([string]$Metodo, [string]$Url, $Cuerpo = $null) {
    $p = @{ Method = $Metodo; Uri = $Url; UseBasicParsing = $true; ErrorAction = 'Stop'; TimeoutSec = 180 }
    if ($null -ne $Cuerpo) {
        $p.Body = [Text.Encoding]::UTF8.GetBytes(($Cuerpo | ConvertTo-Json -Depth 8 -Compress))
        $p.ContentType = 'application/json; charset=utf-8'
    }
    try {
        $r = Invoke-WebRequest @p
        $texto = $r.Content; if ($texto -is [byte[]]) { $texto = [Text.Encoding]::UTF8.GetString($texto) }
        return [pscustomobject]@{ Estado = [int]$r.StatusCode; Json = (ConvertirJson $texto) }
    } catch {
        $respuesta = $_.Exception.Response
        if ($null -eq $respuesta) { throw }
        return [pscustomobject]@{ Estado = [int]$respuesta.StatusCode; Json = (ConvertirJson $_.ErrorDetails.Message) }
    }
}
function ConvertirJson($texto) { if ([string]::IsNullOrWhiteSpace($texto)) { $null } else { try { $texto | ConvertFrom-Json } catch { $null } } }

function Esperar-Salud([string]$Url, [int]$Segundos = 120) {
    $limite = (Get-Date).AddSeconds($Segundos)
    while ((Get-Date) -lt $limite) {
        try { if ((Llamar GET "$Url/health").Estado -eq 200) { return $true } } catch { }
        Start-Sleep -Seconds 2
    }
    return $false
}

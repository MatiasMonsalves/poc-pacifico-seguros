# Revisa si este equipo Windows puede ejecutar la fábrica de migración (WSL2 + Docker).
# No instala ni cambia nada. Ejecutar en PowerShell (no requiere administrador):
#   powershell -ExecutionPolicy Bypass -File revisar-windows.ps1
# Compatible con Windows PowerShell 5.1 (el que trae Windows 10).

$ErrorActionPreference = 'SilentlyContinue'
if ($PSVersionTable.PSVersion.Major -lt 6) { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 }
$script:errores = 0
$script:avisos = 0
function Ok($t)    { Write-Host "  [OK]    $t" -ForegroundColor Green }
function Aviso($t) { Write-Host "  [AVISO] $t" -ForegroundColor Yellow; $script:avisos++ }
function Falla($t) { Write-Host "  [FALTA] $t" -ForegroundColor Red; $script:errores++ }

Write-Host ""
Write-Host "Revisión del equipo para la fábrica de migración" -ForegroundColor Cyan
Write-Host ""

# --- Windows ---------------------------------------------------------------
$so = Get-CimInstance Win32_OperatingSystem
$cv = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
$build = [int]$so.BuildNumber
$version = $cv.DisplayVersion
if (-not $version) { $version = $cv.ReleaseId }
$edicion = $cv.EditionID
Write-Host "Windows: $($so.Caption) $version (build $build.$($cv.UBR)), edición $edicion"

if (-not [Environment]::Is64BitOperatingSystem) { Falla "Windows de 64 bits" } else { Ok "Windows de 64 bits" }

if ($build -lt 19041) {
    Falla "WSL2 necesita Windows 10 versión 2004 (build 19041) o superior. Actualice Windows (Windows Update) a 22H2."
} elseif ($build -lt 19045 -and $build -lt 22000) {
    Aviso "Windows 10 build ${build}: funciona WSL2, pero conviene actualizar a 22H2 (build 19045). Docker Desktop exige 22H2."
} else {
    Ok "Versión de Windows compatible con WSL2"
}
if ($build -ge 22000 -and $build -lt 22631) {
    Aviso "Windows 11 build ${build}: WSL2 funciona, pero Docker Desktop exige Windows 11 23H2 (build 22631) o superior. Actualice con Windows Update o use la opción recomendada (Docker Engine dentro de WSL2)."
}
if ($build -lt 22000) {
    Aviso "Windows 10 ya no recibe soporte general de Microsoft (octubre de 2025). Docker Desktop solo soporta versiones con soporte vigente; Docker Engine dentro de WSL2 (opción recomendada) no depende de eso."
}
if ($edicion -match 'Core|Home') {
    Aviso "Edición Home: Docker Desktop no la soporta. Use la opción recomendada (Docker Engine dentro de WSL2), que sí funciona."
}

# --- Hardware --------------------------------------------------------------
$cs = Get-CimInstance Win32_ComputerSystem
$ramGb = [math]::Round($cs.TotalPhysicalMemory / 1GB)
if ($ramGb -lt 8) { Falla "Memoria RAM: $ramGb GB. Se necesitan al menos 8 GB (SQL Server en Docker usa unos 2 GB)." }
elseif ($ramGb -lt 16) { Aviso "Memoria RAM: $ramGb GB. Funciona; con 16 GB va más holgado." }
else { Ok "Memoria RAM: $ramGb GB" }

$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
if ($cs.HypervisorPresent) {
    Ok "Virtualización activa (hipervisor presente)"
} elseif ($cpu.VirtualizationFirmwareEnabled) {
    Ok "Virtualización habilitada en la BIOS/UEFI"
} else {
    Falla "La virtualización no está habilitada en la BIOS/UEFI (Intel VT-x / AMD-V). Actívela o pida a TI que lo haga. Se ve en Administrador de tareas > Rendimiento > CPU > Virtualización."
}
if (-not $cs.HypervisorPresent -and $cpu.SecondLevelAddressTranslationExtensions -eq $false) {
    Falla "El procesador no informa SLAT, requisito de WSL2."
}

$disco = Get-PSDrive C
$libreGb = [math]::Round($disco.Free / 1GB)
if ($libreGb -lt 15) { Falla "Espacio libre en C: $libreGb GB. Se necesitan unos 15 GB (WSL, imágenes de Docker y compilaciones)." }
else { Ok "Espacio libre en C: $libreGb GB" }

# --- Permisos --------------------------------------------------------------
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$esAdminLocal = (whoami /groups) -match 'S-1-5-32-544'
if ($admin) { Ok "PowerShell abierto como administrador" }
elseif ($esAdminLocal) { Ok "Su usuario es administrador local (abra PowerShell 'como administrador' para instalar WSL)" }
else { Aviso "Su usuario no es administrador: para instalar WSL ('wsl --install') necesitará a TI." }

# --- WSL -------------------------------------------------------------------
$env:WSL_UTF8 = '1'
$wslVersion = (wsl.exe --version 2>$null | Out-String)
if ($LASTEXITCODE -eq 0 -and $wslVersion -match '(\d+\.\d+\.\d+)') {
    $v = [version]$Matches[1]
    if ($v -ge [version]'2.1.5') { Ok "WSL $v instalado" }
    else { Aviso "WSL ${v}: actualícelo con 'wsl --update' (Docker Desktop pide 2.1.5 o superior)." }
    $distros = (wsl.exe -l -v 2>$null | Out-String)
    if ($distros -match 'Ubuntu') {
        if ($distros -match 'Ubuntu\S*\s+\S+\s+1\s') { Aviso "Ubuntu está en WSL versión 1: conviértalo con 'wsl --set-version Ubuntu-24.04 2'." }
        else { Ok "Ubuntu instalado en WSL2" }
    } else {
        Aviso "No hay Ubuntu en WSL. Instálelo con: wsl --install -d Ubuntu-24.04"
    }
} else {
    Aviso "WSL no está instalado. En PowerShell como administrador: wsl --install -d Ubuntu-24.04 (y reiniciar)."
}

# --- Docker Desktop (opcional) --------------------------------------------
$dockerDesktop = Test-Path "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
if ($dockerDesktop) {
    Aviso "Docker Desktop está instalado. Si lo usa, active la integración con Ubuntu (Settings > Resources > WSL integration) y NO instale Docker Engine dentro de Ubuntu. Recuerde que en empresas de más de 250 empleados o más de USD 10 millones de ingresos requiere licencia de pago."
    $srv = Get-Service LanmanServer
    if ($srv.StartType -ne 'Automatic') { Aviso "Docker Desktop requiere el servicio 'Servidor' (LanmanServer) en inicio automático." }
}

# --- Puertos ---------------------------------------------------------------
foreach ($p in 1433, 8080, 8081, 5080) {
    $uso = Get-NetTCPConnection -State Listen -LocalPort $p
    if ($uso) {
        $proc = (Get-Process -Id ($uso | Select-Object -First 1).OwningProcess).ProcessName
        Aviso "El puerto $p está en uso por '$proc'. Cámbielo en el archivo .env del proyecto (ver .env.example)."
    }
}
if (Get-Service MSSQLSERVER) { Aviso "Hay un SQL Server instalado en este equipo: si usa el puerto 1433, defina SQL_PORT=14330 en .env." }

# --- Red -------------------------------------------------------------------
foreach ($url in 'https://mcr.microsoft.com/v2/', 'https://download.docker.com/linux/ubuntu/gpg') {
    try {
        Invoke-WebRequest -Uri $url -UseBasicParsing -Method Head -TimeoutSec 15 -ErrorAction Stop | Out-Null
        Ok "Acceso a $url"
    } catch {
        $msg = $_.Exception.Message
        if ($_.Exception.Response) { Ok "Acceso a $url" }
        elseif ($msg -match 'SSL|TLS|certific|trust') { Aviso "Error de certificado con $url : probablemente un proxy corporativo. Pida a TI el certificado raíz (.pem) para usarlo con CA_BUNDLE." }
        else { Aviso "Sin acceso a $url ($msg). Revise la red o el proxy." }
    }
}

Write-Host ""
if ($script:errores -gt 0) {
    Write-Host "Faltan $script:errores requisito(s). Corríjalos antes de instalar." -ForegroundColor Red
    exit 1
}
Write-Host "El equipo cumple los requisitos ($script:avisos aviso(s) para revisar)." -ForegroundColor Green
Write-Host "Siguiente paso (opción recomendada, sin Docker Desktop), en Ubuntu:"
Write-Host "  git clone https://github.com/matiasmonsalves/poc-pacifico-seguros.git && cd poc-pacifico-seguros"
Write-Host "  git checkout poc/estructura-ingenieria-inversa && scripts/instalar-wsl.sh"

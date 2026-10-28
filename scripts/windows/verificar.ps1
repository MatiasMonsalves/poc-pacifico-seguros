# Verificación completa en Windows con Docker Desktop (equivalente a scripts/verificar.sh):
# análisis, transformación VB6 -> .NET 10, validación de ADF, pruebas, entorno local,
# punta a punta y cobertura. Informe en portafolio\VERIFICACION.md, logs en portafolio\logs\.
#
# Uso (en la carpeta del repositorio):
#   powershell -ExecutionPolicy Bypass -File scripts\windows\verificar.ps1 [-SinDocker] [-SinDecompilar]
# Detrás de un proxy con certificado propio: $env:CA_BUNDLE = 'C:\ruta\cert.pem' antes de ejecutar.
param([switch]$SinDocker, [switch]$SinDecompilar)
. (Join-Path $PSScriptRoot 'comun.ps1')
Set-Location $Raiz
$logs = Join-Path $Raiz 'portafolio/logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$filas = New-Object System.Collections.ArrayList
$script:fallos = 0

function Paso([string]$Nombre, [string]$Log, [scriptblock]$Accion) {
    Write-Host -NoNewline "> $Nombre ... "
    $ruta = Join-Path $logs $Log
    try {
        & $Accion *>&1 | ForEach-Object { "$_" } | Out-File -FilePath $ruta -Encoding utf8
        Write-Host 'OK' -ForegroundColor Green
        [void]$filas.Add("| $Nombre | OK | ``portafolio/logs/$Log`` |")
    } catch {
        "ERROR: $($_.Exception.Message)" | Out-File -FilePath $ruta -Encoding utf8 -Append
        Write-Host "FALLA (ver portafolio\logs\$Log)" -ForegroundColor Red
        [void]$filas.Add("| $Nombre | **FALLA** | ``portafolio/logs/$Log`` |")
        $script:fallos++
    }
}

$argsRequisitos = @{}; if ($SinDocker) { $argsRequisitos.SinDocker = $true }
& (Join-Path $PSScriptRoot 'requisitos.ps1') @argsRequisitos
if ($LASTEXITCODE -ne 0) { exit 1 }
Write-Host ''

Paso '1. Análisis del portafolio (inventario + REA + SSIS->ADF)' 'analisis.log' {
    $a = @('tools/portafolio/portafolio.py', 'analizar'); if (-not $SinDecompilar -and -not $SinDocker) { $a += '--decompilar' }
    Invocar-Python $a
}
Paso '2. Transformación VB6 -> .NET 10 (generar y compilar)' 'vb62net.log' {
    foreach ($vbp in Get-ChildItem (Join-Path $Raiz 'sistemas') -Recurse -Filter *.vbp | Where-Object { $_.FullName -match '[\\/]fuentes[\\/]' }) {
        $sistema = ($vbp.FullName.Substring($Raiz.Length + 1) -split '[\\/]')[1]
        $salida = "sistemas/$sistema/transformacion"
        $argsVb = @('tools/vb62net/vb62net.py', $vbp.FullName, '--salida', $salida, '--factoria', $sistema)
        if (Test-Path (Join-Path $Raiz "sistemas/$sistema/reingenieria/vb6graph/grafo.db")) { $argsVb += @('--grafo', "sistemas/$sistema/reingenieria/vb6graph") }
        Invocar-Python $argsVb
        if (-not $SinDocker) {
            foreach ($proyecto in Get-ChildItem (Join-Path $Raiz $salida) -Directory -Filter *.Generado) {
                Invocar-Dotnet "$salida/$($proyecto.Name)" @('build', '-nologo', '-v', 'q')
            }
        }
    }
}
Paso '3. Validación de los pipelines ADF' 'validar_adf.log' {
    $carpetas = @(Get-ChildItem (Join-Path $Raiz 'sistemas') -Directory | ForEach-Object { Join-Path $_.FullName 'adf' } | Where-Object { Test-Path $_ })
    Invocar-Python (@('tools/ssis2adf/validar_adf.py') + $carpetas)
}
if (-not $SinDocker) {
    Paso '4. Pruebas unitarias y de paridad (.NET 10)' 'pruebas.log' {
        $carpetas = @(Get-ChildItem (Join-Path $Raiz 'sistemas') -Directory | ForEach-Object { "sistemas/$($_.Name)/app" } | Where-Object { Test-Path (Join-Path $Raiz $_) })
        foreach ($c in $carpetas + @('adf-emulador.Pruebas', 'tools/vb62net/Vb62Net.Pruebas')) { "== $c"; Invocar-Dotnet $c @('test') }
    }
    Paso '5. Entorno local (docker compose)' 'compose.log' {
        $compose = Comando-Compose
        & docker @compose up -d --build; Exigir 'docker compose up'
        if (-not (Esperar-Salud $ApiUrl 180) -or -not (Esperar-Salud $GenUrl 60)) { throw "Las apps no responden en $ApiUrl / $GenUrl" }
    }
    Paso '6. Pruebas de punta a punta (demo.ps1)' 'demo.log' {
        & (Get-Process -Id $PID).Path -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'demo.ps1'); Exigir 'demo.ps1'
    }
    Paso '7. Cobertura VB6 -> app terminada' 'cobertura.log' {
        foreach ($cfg in Get-ChildItem (Join-Path $Raiz 'sistemas') -Recurse -Depth 1 -Filter sistema.json) {
            $url = (Get-Content $cfg.FullName -Raw -Encoding UTF8 | ConvertFrom-Json).appUrl
            $mapeo = Join-Path $cfg.DirectoryName 'transformacion/mapeo.json'
            if (-not $url -or -not (Test-Path $mapeo)) { continue }
            $url = $url -replace 'http://localhost:8080', $ApiUrl
            Invocar-Python @('tools/vb62net/cobertura.py', $mapeo, "$url/openapi/v1.json", '--salida', (Join-Path $cfg.DirectoryName 'transformacion/COBERTURA.md'))
        }
    }
}

Paso '8. Plan y trazabilidad (grafo vb6graph)' 'plan.log' {
    foreach ($s in Get-ChildItem (Join-Path $Raiz 'sistemas') -Directory) {
        if (Test-Path (Join-Path $s.FullName 'reingenieria/vb6graph/grafo.db')) { Invocar-Python @('tools/vb6graph_puente/plan.py', $s.FullName) }
    }
}

# Informe
$md = New-Object System.Collections.ArrayList
[void]$md.Add('# Verificación de la fábrica de migración'); [void]$md.Add('')
[void]$md.Add("Ejecutada el $(Get-Date -Format 'dd-MM-yyyy HH:mm') con ``scripts\windows\verificar.ps1`` (Windows + Docker Desktop).")
[void]$md.Add(''); [void]$md.Add('| Paso | Resultado | Log |'); [void]$md.Add('|---|---|---|')
foreach ($f in $filas) { [void]$md.Add($f) }
[void]$md.Add(''); [void]$md.Add('## Resultados'); [void]$md.Add(''); [void]$md.Add('- Portafolio: [PORTAFOLIO.md](PORTAFOLIO.md)')
foreach ($patron in @('transformacion\MAPEO_VB6_NET.md', 'transformacion/COBERTURA.md', 'adf\REPORTE_CONVERSION.md')) {
    foreach ($s in Get-ChildItem (Join-Path $Raiz 'sistemas') -Directory) {
        $archivo = Join-Path $s.FullName $patron
        if (Test-Path $archivo) { $rel = "sistemas/$($s.Name)/" + ($patron -replace '\\', '/'); [void]$md.Add("- [$rel](../$rel)") }
    }
}
$demoLog = Join-Path $logs 'demo.log'
if (-not $SinDocker -and (Test-Path $demoLog)) {
    [void]$md.Add(''); [void]$md.Add('### Punta a punta'); [void]$md.Add(''); [void]$md.Add('```')
    foreach ($l in Get-Content $demoLog -Encoding UTF8) { if ($l -match 'OK |FALLA|verificac') { [void]$md.Add($l) } }
    [void]$md.Add('```')
}
[IO.File]::WriteAllLines((Join-Path $Raiz 'portafolio/VERIFICACION.md'), [string[]]$md, (New-Object Text.UTF8Encoding($false)))

Write-Host ''
if ($script:fallos -eq 0) { Write-Host 'Todo verificado. Informe: portafolio\VERIFICACION.md' -ForegroundColor Green; exit 0 }
Write-Host "$script:fallos paso(s) fallaron. Informe: portafolio\VERIFICACION.md" -ForegroundColor Red
exit 1

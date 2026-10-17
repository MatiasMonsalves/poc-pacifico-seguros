# Pruebas de punta a punta contra el entorno de docker compose (equivalente a scripts/demo.sh).
# Termina con código 1 si algún resultado no es el esperado.
. (Join-Path $PSScriptRoot 'comun.ps1')
$ErrorActionPreference = 'Continue'
$script:fallos = 0

function Titulo($t) { Write-Host ''; Write-Host "== $t" -ForegroundColor Cyan }
function Verificar($descripcion, $obtenido, $esperado) {
    if ("$obtenido" -eq "$esperado") { Write-Host "   OK    ${descripcion}: $obtenido" -ForegroundColor Green }
    else { Write-Host "   FALLA ${descripcion}: se obtuvo '$obtenido', se esperaba '$esperado'" -ForegroundColor Red; $script:fallos++ }
}
function Actividades($carga) {
    foreach ($a in $carga.actividades) {
        $detalle = ''; if ($a.error) { $detalle = "$($a.error)"; if ($detalle.Length -gt 90) { $detalle = $detalle.Substring(0, 90) } }
        Write-Host ('      {0,-28} {1,-10} {2}' -f $a.nombre, $a.estado, $detalle)
    }
}
function EstadoDe($carga, $nombre) { ($carga.actividades | Where-Object { $_.nombre -eq $nombre } | Select-Object -First 1).estado }

if (-not (Esperar-Salud $ApiUrl)) { Write-Host "La API no responde en $ApiUrl" -ForegroundColor Red; exit 1 }

Titulo 'Consulta de pólizas (antes: SQL concatenado en frmPolizas.frm)'
Verificar 'Pólizas del cliente 1' (Llamar GET "$ApiUrl/api/clientes/1/polizas").Json.polizas[0].numPoliza 'POL-0001'
Verificar 'Intento de inyección SQL' (Llamar GET "$ApiUrl/api/clientes/1%20OR%201=1/polizas").Estado 404

Titulo 'Cotización (antes: componente COM Pacifico.Tarificador .NET Framework 4.8)'
Verificar 'P1 redondeo al par como el legado (AUTO, 23 años, 600 UF)' `
    (Llamar POST "$ApiUrl/api/cotizaciones" @{ idCliente = 5; tipoSeguro = 'auto'; sumaAsegurada = 600; siniestros = 0 }).Json.prima '33.34'
Verificar 'P9 edad estilo VB6 DateDiff (nacido 20-12-2001)' `
    (Llamar POST "$ApiUrl/api/cotizaciones" @{ idCliente = 6; tipoSeguro = 'AUTO'; sumaAsegurada = 1000; siniestros = 0 }).Json.edad 25
Verificar 'Tipo de seguro inválido' `
    (Llamar POST "$ApiUrl/api/cotizaciones" @{ idCliente = 1; tipoSeguro = 'MOTO'; sumaAsegurada = 1000; siniestros = 0 }).Estado 400

Titulo 'Carga válida en ADF (antes: Shell dtexec sin ver el resultado)'
$r = (Llamar POST "$ApiUrl/api/cargas" @{ archivo = 'polizas_20261017.csv'; fechaProceso = '2026-10-17'; esperar = $true }).Json
Actividades $r
Verificar 'Estado del pipeline' $r.estado 'Succeeded'
Verificar 'Póliza nueva POL-0005 del cliente 5' (Llamar GET "$ApiUrl/api/clientes/5/polizas").Json.polizas[0].numPoliza 'POL-0005'

Titulo 'Carga con RUT inexistente (P6 + P7: rama de error y Fail)'
$r = (Llamar POST "$ApiUrl/api/cargas" @{ archivo = 'polizas_rut_invalido.csv'; fechaProceso = '2026-10-17'; esperar = $true }).Json
Actividades $r
Verificar 'Estado del pipeline' $r.estado 'Failed'
Verificar 'Se ejecutó Registrar Error' (EstadoDe $r 'Registrar Error') 'Succeeded'

Titulo 'Carga con formato numérico inválido'
$r = (Llamar POST "$ApiUrl/api/cargas" @{ archivo = 'polizas_formato_invalido.csv'; esperar = $true }).Json
Actividades $r
Verificar 'Estado del pipeline' $r.estado 'Failed'
Verificar 'Falla en la copia' (EstadoDe $r 'Cargar CSV a Staging') 'Failed'

Titulo 'Carga asíncrona: 202 + consulta de estado'
$inicio = Llamar POST "$ApiUrl/api/cargas" @{ archivo = 'polizas_20261017.csv' }
Verificar 'Respuesta 202 Accepted' $inicio.Estado 202
Start-Sleep -Seconds 5
Verificar 'Estado consultado por runId' (Llamar GET "$ApiUrl/api/cargas/$($inicio.Json.runId)").Json.estado 'Succeeded'

Titulo 'Pólizas: app generada automáticamente por vb62net'
if (-not (Esperar-Salud $GenUrl 60)) { Write-Host "La app generada no responde en $GenUrl" -ForegroundColor Red; $script:fallos++ }
Verificar 'Buscar (SQL parametrizado)' (Llamar GET "$GenUrl/api/polizas/buscar?Cliente=1").Json.filas[0].NumPoliza 'POL-0001'
Verificar 'Intento de inyección SQL rechazado' (Llamar GET "$GenUrl/api/polizas/buscar?Cliente=1%20OR%201%3D1").Estado 400
Verificar 'Cotizar queda pendiente (lógica COM)' `
    (Llamar POST "$GenUrl/api/polizas/cotizar" @{ Cliente = '5'; Tipo = 'AUTO'; Suma = '600'; Siniestros = '0' }).Estado 501
$run = (Llamar POST "$GenUrl/api/polizas/cargar").Json.runId
Start-Sleep -Seconds 5
Verificar 'Cargar (Shell dtexec -> pipeline ADF)' (Llamar GET "$ApiUrl/api/cargas/$run").Json.estado 'Succeeded'

Titulo 'Siniestros: pipeline maestro -> pipeline hijo en el emulador de ADF'
$fab = "$AdfUrl/subscriptions/sub-poc/resourceGroups/rg-poc/providers/Microsoft.DataFactory/factories/siniestros"
$run = (Llamar POST "$fab/pipelines/PL_Maestro_Siniestros/createRun" @{ FechaCorte = '2026-10-17' }).Json.runId
$estado = ''
for ($i = 0; $i -lt 30; $i++) {
    $estado = (Llamar GET "$fab/pipelineruns/$run").Json.status
    if ($estado -eq 'Succeeded' -or $estado -eq 'Failed') { break }
    Start-Sleep -Seconds 1
}
Verificar 'Estado del pipeline maestro' $estado 'Succeeded'
$hijo = ((Llamar POST "$fab/pipelineruns/$run/queryActivityruns").Json.value | Where-Object { $_.activityType -eq 'ExecutePipeline' }).output.pipelineRunId
$actividadesHijo = (Llamar POST "$fab/pipelineruns/$hijo/queryActivityruns").Json.value
Verificar 'Filas copiadas de CoreLegado a Siniestros (solo vigentes)' ($actividadesHijo | Where-Object { $_.activityType -eq 'Copy' }).output.rowsCopied 3
Verificar 'Script Task marcado como pendiente de migrar' `
    ($null -ne ($actividadesHijo | Where-Object { $_.activityName -eq 'Validar totales' }).output.advertencia) 'True'

Titulo 'Resultado'
if ($script:fallos -eq 0) { Write-Host '   Todas las verificaciones pasaron' -ForegroundColor Green; exit 0 }
Write-Host "   $script:fallos verificación(es) fallaron" -ForegroundColor Red
exit 1

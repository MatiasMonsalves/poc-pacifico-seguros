#!/usr/bin/env bash
# Demostración de punta a punta contra el entorno de docker compose:
# la API .NET 10 (reemplazo de la app VB6) dispara el pipeline de ADF convertido desde SSIS.
# Termina con código 1 si algún resultado no es el esperado.
set -uo pipefail
API=${API:-http://localhost:8080}
FALLOS=0

titulo() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
verificar() { # descripción, valor obtenido, valor esperado
  if [[ "$2" == "$3" ]]; then printf '   \033[32mOK\033[0m  %s: %s\n' "$1" "$2"
  else printf '   \033[31mFALLA\033[0m %s: se obtuvo "%s", se esperaba "%s"\n' "$1" "$2" "$3"; FALLOS=$((FALLOS + 1)); fi
}
campo() { python3 -c "import json,sys; d=json.load(sys.stdin); print(eval('d' + sys.argv[1]))" "$1"; }
estado_de() { python3 -c "import json,sys; print(next(a['estado'] for a in json.load(sys.stdin)['actividades'] if a['nombre']==sys.argv[1]))" "$1"; }
post() { curl -s -X POST "$API$1" -H 'Content-Type: application/json' -d "$2"; }
actividades() { python3 -c "
import json,sys
d=json.load(sys.stdin)
for a in d['actividades']: print('     ', a['nombre'].ljust(28), a['estado'].ljust(10), (a.get('error') or '')[:90])"; }

for i in $(seq 1 60); do curl -sf "$API/health" >/dev/null && break; sleep 2; done

titulo "Consulta de pólizas (antes: SQL concatenado en frmPolizas.frm)"
verificar "Pólizas del cliente 1" "$(curl -s "$API/api/clientes/1/polizas" | campo "['polizas'][0]['numPoliza']")" "POL-0001"
verificar "Intento de inyección SQL" "$(curl -s -o /dev/null -w '%{http_code}' "$API/api/clientes/1%20OR%201=1/polizas")" "404"

titulo "Cotización (antes: componente COM Pacifico.Tarificador .NET Framework 4.8)"
verificar "P1 redondeo al par como el legado (AUTO, 23 años, 600 UF)" \
  "$(post /api/cotizaciones '{"idCliente":5,"tipoSeguro":"auto","sumaAsegurada":600,"siniestros":0}' | campo "['prima']")" "33.34"
verificar "P9 edad estilo VB6 DateDiff (nacido 20-12-2001)" \
  "$(post /api/cotizaciones '{"idCliente":6,"tipoSeguro":"AUTO","sumaAsegurada":1000,"siniestros":0}' | campo "['edad']")" "25"
verificar "Tipo de seguro inválido" \
  "$(post /api/cotizaciones '{"idCliente":1,"tipoSeguro":"MOTO","sumaAsegurada":1000,"siniestros":0}' | campo "['status']")" "400"

titulo "Carga válida en ADF (antes: Shell dtexec sin ver el resultado)"
R=$(post /api/cargas '{"archivo":"polizas_20261017.csv","fechaProceso":"2026-10-17","esperar":true}')
echo "$R" | actividades
verificar "Estado del pipeline" "$(echo "$R" | campo "['estado']")" "Succeeded"
verificar "Póliza nueva POL-0005 del cliente 5" "$(curl -s "$API/api/clientes/5/polizas" | campo "['polizas'][0]['numPoliza']")" "POL-0005"

titulo "Carga con RUT inexistente (P6 + P7: rama de error y Fail)"
R=$(post /api/cargas '{"archivo":"polizas_rut_invalido.csv","fechaProceso":"2026-10-17","esperar":true}')
echo "$R" | actividades
verificar "Estado del pipeline" "$(echo "$R" | campo "['estado']")" "Failed"
verificar "Se ejecutó Registrar Error" "$(echo "$R" | estado_de "Registrar Error")" "Succeeded"

titulo "Carga con formato numérico inválido"
R=$(post /api/cargas '{"archivo":"polizas_formato_invalido.csv","esperar":true}')
echo "$R" | actividades
verificar "Estado del pipeline" "$(echo "$R" | campo "['estado']")" "Failed"
verificar "Falla en la copia" "$(echo "$R" | estado_de "Cargar CSV a Staging")" "Failed"

titulo "Carga asíncrona: 202 + consulta de estado"
RUN=$(post /api/cargas '{"archivo":"polizas_20261017.csv"}' | campo "['runId']")
sleep 5
verificar "Estado consultado por runId" "$(curl -s "$API/api/cargas/$RUN" | campo "['estado']")" "Succeeded"

titulo "Siniestros: pipeline maestro → pipeline hijo (Execute Package → Execute Pipeline) en el emulador"
ADF=${ADF:-http://localhost:5080}
FAB="$ADF/subscriptions/sub-poc/resourceGroups/rg-poc/providers/Microsoft.DataFactory/factories/siniestros"
RUN=$(curl -s -X POST "$FAB/pipelines/PL_Maestro_Siniestros/createRun" -H 'Content-Type: application/json' -d '{"FechaCorte":"2026-10-17"}' | campo "['runId']")
for i in $(seq 1 30); do
  ESTADO=$(curl -s "$FAB/pipelineruns/$RUN" | campo "['status']")
  [[ "$ESTADO" == "Succeeded" || "$ESTADO" == "Failed" ]] && break; sleep 1
done
ACT=$(curl -s -X POST "$FAB/pipelineruns/$RUN/queryActivityruns")
verificar "Estado del pipeline maestro" "$ESTADO" "Succeeded"
HIJO=$(echo "$ACT" | python3 -c "import json,sys; print(next(a['output']['pipelineRunId'] for a in json.load(sys.stdin)['value'] if a['activityType']=='ExecutePipeline'))")
verificar "Filas copiadas de CoreLegado a Siniestros (solo vigentes)" \
  "$(curl -s -X POST "$FAB/pipelineruns/$HIJO/queryActivityruns" | python3 -c "import json,sys; print(next(a['output']['rowsCopied'] for a in json.load(sys.stdin)['value'] if a['activityType']=='Copy'))")" "3"
verificar "Script Task marcado como pendiente de migrar" \
  "$(curl -s -X POST "$FAB/pipelineruns/$HIJO/queryActivityruns" | python3 -c "import json,sys; print('advertencia' in next(a['output'] for a in json.load(sys.stdin)['value'] if a['activityName']=='Validar totales'))")" "True"

titulo "Resultado"
if [[ $FALLOS -eq 0 ]]; then echo "   Todas las verificaciones pasaron"; else echo "   $FALLOS verificación(es) fallaron"; exit 1; fi

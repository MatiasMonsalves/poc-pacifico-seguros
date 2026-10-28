#!/usr/bin/env bash
# Verificación completa de la fábrica: análisis, transformación VB6 → .NET 10, SSIS → ADF,
# pruebas, entorno local y pruebas de punta a punta. Deja el informe en portafolio/VERIFICACION.md.
#
# Uso: scripts/verificar.sh [--sin-docker] [--sin-decompilar]
#   --sin-docker      solo pasos que no levantan el entorno (análisis, transformación, validación de ADF)
#   --sin-decompilar  no decompila con ILSpy (más rápido)
# Detrás de un proxy con certificado propio, defina CA_BUNDLE=/ruta/ca.crt.
set -uo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"
LOGS="$RAIZ/portafolio/logs"; mkdir -p "$LOGS"
INFORME="$RAIZ/portafolio/VERIFICACION.md"
CON_DOCKER=1; DECOMPILAR="--decompilar"
for a in "$@"; do
  case "$a" in --sin-docker) CON_DOCKER=0 ;; --sin-decompilar) DECOMPILAR="" ;; *) echo "Opción desconocida: $a"; exit 2 ;; esac
done
[[ -f .env ]] && set -a && . ./.env && set +a
API_URL="http://localhost:${API_PORT:-8080}"; GEN_URL="http://localhost:${GEN_PORT:-8081}"
COMPOSE=(docker compose -f docker-compose.yml); [[ -n "${CA_BUNDLE:-}" ]] && COMPOSE+=(-f docker-compose.proxy.yml)
FILAS=(); FALLOS=0

paso() { # nombre, archivo de log, comando...
  local nombre="$1" log="$LOGS/$2"; shift 2
  printf '\033[1m▶ %s\033[0m ... ' "$nombre"
  if "$@" >"$log" 2>&1; then
    printf '\033[32mOK\033[0m\n'; FILAS+=("| $nombre | OK | \`portafolio/logs/$(basename "$log")\` |")
  else
    printf '\033[31mFALLA\033[0m (ver %s)\n' "$log"; FILAS+=("| $nombre | **FALLA** | \`portafolio/logs/$(basename "$log")\` |"); FALLOS=$((FALLOS + 1))
  fi
}

transformar_vb6() {
  local ok=0
  shopt -s globstar nullglob
  for vbp in sistemas/*/fuentes/**/*.vbp; do
    local sistema; sistema=$(echo "$vbp" | cut -d/ -f2)
    local grafo=(); [[ -f "sistemas/$sistema/reingenieria/vb6graph/grafo.db" ]] && grafo=(--grafo "sistemas/$sistema/reingenieria/vb6graph")
    python3 tools/vb62net/vb62net.py "$vbp" --salida "sistemas/$sistema/transformacion" --factoria "$sistema" "${grafo[@]}" || ok=1
    for proyecto in sistemas/"$sistema"/transformacion/*.Generado; do
      DOTNET_DIR="$proyecto" scripts/dotnet.sh build -nologo -v q || ok=1
    done
  done
  return $ok
}

validar_adf() { python3 tools/ssis2adf/validar_adf.py sistemas/*/adf; }

pruebas_dotnet() {
  local ok=0
  for d in sistemas/*/app adf-emulador.Pruebas tools/vb62net/Vb62Net.Pruebas; do
    [[ -d "$d" ]] || continue
    echo "== $d"; DOTNET_DIR="$d" scripts/dotnet.sh test || ok=1
  done
  return $ok
}

cobertura_vb6() {
  local ok=0
  for cfg in sistemas/*/sistema.json; do
    local dir url; dir=$(dirname "$cfg")
    url=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('appUrl',''))" "$cfg")
    [[ -n "$url" && -f "$dir/transformacion/mapeo.json" ]] || continue
    url="${url/http:\/\/localhost:8080/$API_URL}"
    python3 tools/vb62net/cobertura.py "$dir/transformacion/mapeo.json" "$url/openapi/v1.json" --salida "$dir/transformacion/COBERTURA.md" || ok=1
  done
  return $ok
}

plan_trazabilidad() {
  local ok=0
  for g in sistemas/*/reingenieria/vb6graph/grafo.db; do
    [[ -f "$g" ]] || continue
    python3 tools/vb6graph_puente/plan.py "$(dirname "$(dirname "$(dirname "$g")")")" || ok=1
  done
  return $ok
}

levantar() {
  "${COMPOSE[@]}" up -d --build && for i in $(seq 1 60); do curl -sf "$API_URL/health" >/dev/null && curl -sf "$GEN_URL/health" >/dev/null && return 0; sleep 2; done; return 1
}

scripts/requisitos.sh $([[ $CON_DOCKER -eq 0 ]] && echo --sin-docker) || exit 1
echo
paso "1. Análisis del portafolio (inventario + REA + SSIS→ADF)" analisis.log python3 tools/portafolio/portafolio.py analizar $DECOMPILAR
paso "2. Transformación VB6 → .NET 10 (generar y compilar)" vb62net.log transformar_vb6
paso "3. Validación de los pipelines ADF" validar_adf.log validar_adf
if [[ $CON_DOCKER -eq 1 ]]; then
  paso "4. Pruebas unitarias y de paridad (.NET 10)" pruebas.log pruebas_dotnet
  paso "5. Entorno local (docker compose)" compose.log levantar
  paso "6. Pruebas de punta a punta (scripts/demo.sh)" demo.log scripts/demo.sh
  paso "7. Cobertura VB6 → app terminada" cobertura.log cobertura_vb6
fi
paso "8. Plan y trazabilidad (grafo vb6graph)" plan.log plan_trazabilidad

{
  echo "# Verificación de la fábrica de migración"
  echo
  echo "Ejecutada el $(date '+%d-%m-%Y %H:%M') con \`scripts/verificar.sh $*\`."
  echo
  echo "| Paso | Resultado | Log |"; echo "|---|---|---|"
  printf '%s\n' "${FILAS[@]}"
  echo
  echo "## Resultados"
  echo
  echo "- Portafolio: [PORTAFOLIO.md](PORTAFOLIO.md)"
  for m in sistemas/*/transformacion/MAPEO_VB6_NET.md; do [[ -f "$m" ]] && echo "- Transformación VB6 → .NET: [$m](../$m)"; done
  for m in sistemas/*/transformacion/COBERTURA.md; do [[ -f "$m" ]] && echo "- Cobertura: [$m](../$m)"; done
  for m in sistemas/*/plan/AVANCE.md; do [[ -f "$m" ]] && echo "- Plan y avance: [$m](../$m)"; done
  for m in sistemas/*/adf/REPORTE_CONVERSION.md; do [[ -f "$m" ]] && echo "- SSIS → ADF: [$m](../$m)"; done
  echo
  echo "### Validación de ADF"; echo; echo '```'; cat "$LOGS/validar_adf.log"; echo '```'
  if [[ -f "$LOGS/demo.log" && $CON_DOCKER -eq 1 ]]; then
    echo; echo "### Punta a punta"; echo; echo '```'; sed 's/\x1b\[[0-9;]*m//g' "$LOGS/demo.log" | grep -E "OK|FALLA|verificac"; echo '```'
  fi
} > "$INFORME"

echo
if [[ $FALLOS -eq 0 ]]; then echo "Todo verificado. Informe: portafolio/VERIFICACION.md"
else echo "$FALLOS paso(s) fallaron. Informe: portafolio/VERIFICACION.md"; exit 1; fi

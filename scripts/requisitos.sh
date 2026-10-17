#!/usr/bin/env bash
# Revisa que el equipo tenga lo necesario para levantar y verificar la fábrica.
# Uso: scripts/requisitos.sh [--sin-docker]
set -uo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"
[[ -f .env ]] && set -a && . ./.env && set +a
CON_DOCKER=1; [[ "${1:-}" == "--sin-docker" ]] && CON_DOCKER=0
ERRORES=0
ok()    { printf '  \033[32m✔\033[0m %s\n' "$1"; }
aviso() { printf '  \033[33m!\033[0m %s\n' "$1"; }
error() { printf '  \033[31m✘\033[0m %s\n' "$1"; ERRORES=$((ERRORES + 1)); }

echo "Requisitos"

# Saltos de línea: un clon en Windows sin .gitattributes deja los scripts en CRLF
if grep -q $'\r' scripts/verificar.sh infra/db-init.sh 2>/dev/null; then
  error "Los scripts tienen saltos de línea de Windows (CRLF). Clone de nuevo el repositorio (incluye .gitattributes) o ejecute: git add --renormalize . && git checkout -- ."
else ok "Saltos de línea de los scripts (LF)"; fi

if grep -qi microsoft /proc/version 2>/dev/null; then
  case "$RAIZ" in /mnt/*) aviso "Está en WSL con el repositorio en $RAIZ (disco de Windows): muévalo a su carpeta de Linux (~/) para evitar lentitud y problemas de permisos" ;;
                  *) ok "WSL con el repositorio en el sistema de archivos de Linux" ;; esac
fi

if command -v python3 >/dev/null && python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
  ok "Python $(python3 -c 'import platform; print(platform.python_version())')"
else error "Python 3.9 o superior (comando python3)"; fi

command -v curl >/dev/null && ok "curl" || error "curl"

if command -v rea >/dev/null; then ok "REA $(rea --version 2>/dev/null | head -1)"
else aviso "REA no instalado (opcional): se reutiliza el análisis de binarios guardado. Para instalarlo: npm install -g rea-agents (Node.js >= 22.19)"; fi

if [[ $CON_DOCKER -eq 1 ]]; then
  if ! command -v docker >/dev/null; then
    error "Docker (Docker Desktop en Windows/macOS, Docker Engine en Linux)"
  elif ! docker info >/dev/null 2>&1; then
    error "Docker está instalado pero no responde: inicie Docker Desktop o el servicio docker"
  else
    ok "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null)"
    docker compose version >/dev/null 2>&1 && ok "Docker Compose $(docker compose version --short 2>/dev/null)" \
      || error "Docker Compose v2 (el comando 'docker compose')"
    memoria=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
    if (( memoria < 3800000000 )); then
      error "Docker tiene $((memoria / 1024 / 1024)) MB de memoria; SQL Server necesita al menos 4 GB (Docker Desktop → Settings → Resources)"
    else ok "Memoria para Docker: $((memoria / 1024 / 1024 / 1024)) GB"; fi
    case "$(docker info --format '{{.Architecture}}' 2>/dev/null)" in
      aarch64|arm64) aviso "Equipo ARM (Apple Silicon): SQL Server corre emulado. Active en Docker Desktop: Settings → General → 'Use Rosetta for x86_64/amd64 emulation'" ;;
    esac
    for par in "SQL_PORT:${SQL_PORT:-1433}" "API_PORT:${API_PORT:-8080}" "GEN_PORT:${GEN_PORT:-8081}" "ADF_PORT:${ADF_PORT:-5080}"; do
      variable=${par%%:*}; puerto=${par##*:}
      if (exec 3<>"/dev/tcp/127.0.0.1/$puerto") 2>/dev/null; then
        if docker ps --format '{{.Names}} {{.Ports}}' | grep -E "^poc-pacifico" | grep -q ":$puerto->"; then
          ok "Puerto $puerto (en uso por este mismo entorno)"
        else
          error "El puerto $puerto está ocupado por otro programa: cámbielo en .env ($variable=...), copiando antes .env.example a .env"
        fi
      else ok "Puerto $puerto libre"; fi
    done
  fi
  # Descarga de imágenes y paquetes: detrás de un proxy corporativo con inspección TLS hace falta su certificado
  for url in https://mcr.microsoft.com/v2/ https://api.nuget.org/v3/index.json; do
    if curl -sS -o /dev/null --max-time 15 ${CA_BUNDLE:+--cacert "$CA_BUNDLE"} "$url" 2>/tmp/requisitos-curl.$$; then
      ok "Acceso a ${url#https://}"
    elif grep -qi "certificate" /tmp/requisitos-curl.$$; then
      error "Certificado no válido al acceder a ${url#https://}: probablemente un proxy corporativo. Pida el certificado raíz (.crt/.pem) a TI y ejecute con CA_BUNDLE=/ruta/certificado.pem"
    else
      error "Sin acceso a ${url#https://} ($(tr -d '\n' < /tmp/requisitos-curl.$$)). Revise la red o el proxy (HTTPS_PROXY)"
    fi
    rm -f /tmp/requisitos-curl.$$
  done
fi

if [[ $ERRORES -gt 0 ]]; then echo "Faltan $ERRORES requisito(s)."; exit 1; fi
echo "Todo listo."

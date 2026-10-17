#!/usr/bin/env bash
# Instala en Ubuntu (WSL2 o Linux) lo necesario para la fábrica, SIN Docker Desktop:
# Docker Engine + Compose (gratuitos), git, python3, curl y, opcionalmente, Node.js 22 + REA.
# Uso: scripts/instalar-wsl.sh [--sin-rea]
set -euo pipefail
CON_REA=1; [[ "${1:-}" == "--sin-rea" ]] && CON_REA=0
[[ $EUID -eq 0 ]] && SUDO="" || SUDO="sudo"
. /etc/os-release
[[ "${ID:-}" == "ubuntu" || "${ID_LIKE:-}" == *ubuntu* || "${ID:-}" == "debian" ]] || { echo "Este script es para Ubuntu/Debian"; exit 1; }

echo "== Paquetes base"
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq ca-certificates curl gnupg git python3 >/dev/null

if ! command -v docker >/dev/null; then
  echo "== Docker Engine y Compose (repositorio oficial de Docker)"
  $SUDO install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/$ID/gpg" | $SUDO gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
  $SUDO chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$ID ${VERSION_CODENAME} stable" \
    | $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
else
  echo "== Docker ya instalado: $(docker --version)"
fi
if [[ -n "$SUDO" ]] && ! id -nG "$USER" | grep -qw docker; then
  $SUDO usermod -aG docker "$USER"
  REINICIAR=1
fi

# En WSL, systemd arranca Docker automáticamente al abrir Ubuntu
if grep -qi microsoft /proc/version 2>/dev/null && ! grep -q "systemd=true" /etc/wsl.conf 2>/dev/null; then
  echo "== Activando systemd en WSL (/etc/wsl.conf)"
  printf '[boot]\nsystemd=true\n' | $SUDO tee -a /etc/wsl.conf >/dev/null
  REINICIAR=1
fi

instalar_rea() {
  if ! command -v node >/dev/null || [[ "$(node -p 'process.versions.node.split(".")[0]')" -lt 22 ]]; then
    echo "== Node.js 22 (para REA)"
    curl -fsSL https://deb.nodesource.com/setup_22.x -o /tmp/nodesource_setup.sh || return 1
    ${SUDO:+$SUDO -E} bash /tmp/nodesource_setup.sh >/dev/null || return 1
    $SUDO apt-get install -y -qq nodejs >/dev/null || return 1
  fi
  echo "== REA"
  $SUDO npm install -g rea-agents >/dev/null 2>&1 || return 1
  echo "   $(rea --version 2>/dev/null | head -1)"
}
# REA es opcional: si falla (por ejemplo, el proxy bloquea deb.nodesource.com) la fábrica funciona igual
if [[ $CON_REA -eq 1 ]] && ! instalar_rea; then
  echo "   No se pudo instalar Node.js/REA (opcional). Se usará el análisis de binarios guardado en el repositorio."
fi

echo
if [[ "${REINICIAR:-0}" -eq 1 ]]; then
  echo "Listo. Cierre Ubuntu, ejecute en PowerShell:  wsl --shutdown  y vuelva a abrir Ubuntu."
  echo "Después:  cd poc-pacifico-seguros && scripts/requisitos.sh"
else
  echo "Listo. Siguiente paso:  scripts/requisitos.sh"
fi

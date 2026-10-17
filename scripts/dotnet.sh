#!/usr/bin/env bash
# Ejecuta el CLI de .NET 10 dentro del contenedor oficial del SDK (no requiere instalar .NET).
# Si hay un proxy con CA propia (HTTPS_PROXY + CA_BUNDLE), se le pasa al contenedor.
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
ARGS=(--rm --network host -v "$RAIZ:/src" -v poc-nuget:/root/.nuget/packages -w "/src/${DOTNET_DIR:-}")
if [[ -n "${CA_BUNDLE:-}" ]]; then
  ARGS+=(-e HTTPS_PROXY -e HTTP_PROXY -e NO_PROXY -e SSL_CERT_FILE=/ca.crt -v "$CA_BUNDLE:/ca.crt:ro")
fi
exec docker run "${ARGS[@]}" mcr.microsoft.com/dotnet/sdk:10.0 dotnet "$@"

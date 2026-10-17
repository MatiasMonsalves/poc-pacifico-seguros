#!/bin/bash
# Crea la BD legada "Seguros" (esquema, SPs y datos) si todavía no existe.
set -euo pipefail
SQLCMD=(/opt/mssql-tools18/bin/sqlcmd -C -b -S "${SQL_HOST:-sqlserver}" -U sa -P "$MSSQL_SA_PASSWORD")

for i in $(seq 1 60); do
  "${SQLCMD[@]}" -Q "SELECT 1" >/dev/null 2>&1 && break
  echo "Esperando a SQL Server ($i)..."; sleep 2
done

if [[ "$("${SQLCMD[@]}" -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.databases WHERE name = 'Seguros'")" == "1" ]]; then
  echo "La BD Seguros ya existe; no se reinicializa."
  exit 0
fi

for script in /scripts/*.sql; do
  echo "Ejecutando $(basename "$script")"
  "${SQLCMD[@]}" -i "$script"
done
echo "BD Seguros lista."

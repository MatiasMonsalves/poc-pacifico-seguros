#!/bin/bash
# Crea las BDs legadas de cada sistema (sistemas/<id>/fuentes/db/*.sql) si todavía no existen.
# El nombre de la BD se toma del "CREATE DATABASE" del primer script.
set -euo pipefail
SQLCMD=(/opt/mssql-tools18/bin/sqlcmd -C -b -S "${SQL_HOST:-sqlserver}" -U sa -P "$MSSQL_SA_PASSWORD")

for i in $(seq 1 60); do
  "${SQLCMD[@]}" -Q "SELECT 1" >/dev/null 2>&1 && break
  echo "Esperando a SQL Server ($i)..."; sleep 2
done

for carpeta in /sistemas/*/fuentes/db; do
  [[ -d "$carpeta" ]] || continue
  sistema=$(basename "$(dirname "$(dirname "$carpeta")")")
  scripts=("$carpeta"/*.sql)
  [[ -e "${scripts[0]}" ]] || continue
  bd=$(grep -ohiP "CREATE\s+DATABASE\s+\[?\K\w+" "${scripts[@]}" | head -1 || true)
  if [[ -n "$bd" && "$("${SQLCMD[@]}" -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.databases WHERE name = '$bd'")" == "1" ]]; then
    echo "[$sistema] La BD $bd ya existe; no se reinicializa."
    continue
  fi
  for script in "${scripts[@]}"; do
    echo "[$sistema] Ejecutando $(basename "$script")"
    "${SQLCMD[@]}" -i "$script"
  done
  echo "[$sistema] BD ${bd:-(sin CREATE DATABASE)} lista."
done

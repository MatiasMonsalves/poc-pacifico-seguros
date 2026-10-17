"""Cobertura de la migración VB6 → .NET: ¿cada evento de formulario VB6 tiene su reemplazo?

Compara el mapeo que genera vb62net (mapeo.json) con el documento OpenAPI de la app
.NET terminada. Un endpoint declara qué reemplaza con
`.WithDescription("Reemplaza VB6 <formulario>.<evento>")`.

Uso:
    python cobertura.py <mapeo.json> <openapi.json | http://.../openapi/v1.json> [--salida reporte.md]
Termina con código 1 si falta algún evento.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path


def cargar_openapi(origen: str) -> dict:
    if re.match(r"https?://", origen):
        with urllib.request.urlopen(origen, timeout=10) as r:
            return json.load(r)
    return json.loads(Path(origen).read_text(encoding="utf-8"))


def reemplazos(openapi: dict) -> dict[str, str]:
    encontrados = {}
    for ruta, metodos in openapi.get("paths", {}).items():
        for metodo, op in metodos.items():
            for m in re.finditer(r"Reemplaza VB6 ([\w.]+)", op.get("description", "") or ""):
                encontrados[m.group(1)] = f"{metodo.upper()} {ruta}"
    return encontrados


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mapeo", type=Path)
    p.add_argument("openapi")
    p.add_argument("--salida", type=Path)
    a = p.parse_args(argv[1:])

    mapeo = json.loads(a.mapeo.read_text(encoding="utf-8"))
    hechos = reemplazos(cargar_openapi(a.openapi))
    eventos = [m for m in mapeo if m["clase"] == "evento"]
    filas, faltan = [], 0
    for m in eventos:
        clave = f"{m['modulo']}.{m['nombre']}"
        destino = hechos.get(clave)
        faltan += destino is None
        filas.append(f"| `{clave}` | {m['estado']} → `{m['destino']}` | {('`' + destino + '`') if destino else '**FALTA**'} |")
    lineas = ["# Cobertura VB6 → .NET 10", "",
              f"{len(eventos) - faltan} de {len(eventos)} eventos VB6 tienen reemplazo en la app terminada.", "",
              "| Evento VB6 | Generado por vb62net | App terminada |", "|---|---|---|", *filas, ""]
    texto = "\n".join(lineas)
    if a.salida:
        a.salida.write_text(texto, encoding="utf-8")
    print(texto)
    return 1 if faltan else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

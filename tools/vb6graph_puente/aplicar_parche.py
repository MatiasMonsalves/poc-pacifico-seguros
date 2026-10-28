"""Aplica a la instalación local de vb6graph los parches de tools/vb6graph_puente/parches/.

0001-esquema-y-procedimientos.patch:
  * las tablas se identifican por esquema.tabla (sin esquema se asume dbo): stg.Polizas y dbo.Polizas
    dejan de ser el mismo nodo y desaparece el falso acoplamiento VB6 <-> SSIS;
  * los procedimientos almacenados son nodos propios (kind db_proc) con la arista EXECUTES_PROC,
    en vez de una tabla con object_type=procedure y una arista READS heurística.

Funciona en Windows y Linux; necesita git (usa `git apply`). Es idempotente.

Uso:
    python tools/vb6graph_puente/aplicar_parche.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PARCHES = Path(__file__).resolve().parent / "parches"


def carpeta_instalada() -> Path | None:
    """site-packages de la herramienta vb6graph instalada con `uv tool install`."""
    uv = shutil.which("uv")
    if not uv:
        return None
    r = subprocess.run([uv, "tool", "dir"], capture_output=True, text=True)
    base = Path(r.stdout.strip()) / "vb6graph"
    candidatos = list(base.glob("lib/python*/site-packages")) + list(base.glob("Lib/site-packages"))
    return next((c for c in candidatos if (c / "vb6graph").is_dir()), None)


def main() -> int:
    destino = carpeta_instalada()
    if not destino:
        print("No encontré vb6graph instalado con uv (no es necesario para la demo: se usa el grafo guardado).")
        return 1
    if not shutil.which("git"):
        print("Falta git para aplicar el parche.")
        return 1
    for parche in sorted(PARCHES.glob("*.patch")):
        ya = subprocess.run(["git", "apply", "--reverse", "--check", str(parche)], cwd=destino, capture_output=True)
        if ya.returncode == 0:
            print(f"✔ {parche.name}: ya aplicado")
            continue
        r = subprocess.run(["git", "apply", str(parche)], cwd=destino, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"✘ {parche.name}: no se pudo aplicar (¿otra versión de vb6graph?)\n{r.stderr}")
            return 1
        print(f"✔ {parche.name}: aplicado en {destino / 'vb6graph'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

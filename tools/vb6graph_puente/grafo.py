"""Puente entre vb6graph (grafo de conocimiento VB6 + SSIS) y la fábrica de migración.

vb6graph es la fuente de verdad del assessment: parsea el VB6 con tree-sitter y los .dtsx,
y deja un grafo SQLite con evidencia archivo:línea por nodo y arista, más un reporte HTML
con CSV (inventario, procedimientos, tablas, riesgos, código muerto).

Este módulo:
  * ejecuta vb6graph (index + report) si está instalado, dejando todo en
    sistemas/<id>/reingenieria/vb6graph/ (grafo.db, reporte.html, csv/);
  * si no está instalado, reutiliza lo que ya esté guardado allí;
  * expone el grafo a las demás herramientas (vb62net, plan) con una API simple.

Uso:
    python grafo.py indexar <carpeta_fuentes> <carpeta_salida>
    python grafo.py resumen <carpeta_salida>
"""

from __future__ import annotations

import csv
import json
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

VB6GRAPH = shutil.which("vb6graph")


@dataclass
class Proc:
    id: str
    nombre: str
    modulo: str
    archivo: str
    linea_inicio: int
    linea_fin: int
    evento: bool = False
    ciclomatica: int = 1
    sql: list[dict] = field(default_factory=list)          # [{texto, operacion, linea}]
    lee: list[str] = field(default_factory=list)
    escribe: list[str] = field(default_factory=list)
    llama_a: list[str] = field(default_factory=list)
    sin_resolver: list[str] = field(default_factory=list)   # llamadas con enlace tardío / COM
    muerto: bool = False
    seguro_borrar: bool = False

    @property
    def evidencia(self) -> str:
        return f"{self.archivo}:{self.linea_inicio}-{self.linea_fin}"


@dataclass
class Grafo:
    carpeta: Path
    procs: dict[str, Proc] = field(default_factory=dict)    # clave: "modulo.nombre" en minúsculas
    formularios: list[dict] = field(default_factory=list)   # filas de inventario.csv
    paquetes_ssis: list[dict] = field(default_factory=list)
    tablas: list[dict] = field(default_factory=list)        # filas de tablas.csv (dueños de lectura/escritura)
    riesgos: list[dict] = field(default_factory=list)
    resolucion_llamadas: str = ""

    def proc(self, modulo: str, nombre: str) -> Proc | None:
        return self.procs.get(f"{modulo}.{nombre}".lower())

    def muertos(self) -> list[Proc]:
        return [p for p in self.procs.values() if p.muerto]


def indexar(fuentes: Path, salida: Path) -> bool:
    """Indexa con vb6graph. Devuelve False (sin error) si vb6graph no está instalado."""
    if not VB6GRAPH:
        return False
    salida.mkdir(parents=True, exist_ok=True)
    db = salida / "grafo.db"
    db.unlink(missing_ok=True)
    subprocess.run([VB6GRAPH, "index", str(fuentes), "--out", str(db)], check=True,
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
    shutil.rmtree(salida / "csv", ignore_errors=True)
    subprocess.run([VB6GRAPH, "report", str(db), "--out", str(salida / "reporte.html"), "--csv-dir", str(salida / "csv")],
                   check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return True


def _csv(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def cargar(carpeta: Path) -> Grafo | None:
    """Carga el grafo guardado en carpeta (grafo.db + csv/). None si no hay grafo."""
    db = carpeta / "grafo.db"
    if not db.exists():
        return None
    g = Grafo(carpeta)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    nodos = {r["id"]: r for r in con.execute("SELECT * FROM nodes")}

    def nombre_contenedor(proc_id: str) -> str:
        return proc_id.split("/", 1)[1].split(".", 1)[0]

    for r in nodos.values():
        if r["kind"] != "proc":
            continue
        modulo = next((n["name"] for n in nodos.values()
                       if n["kind"] in ("form", "module", "class", "usercontrol")
                       and n["id"].split(":", 1)[1] == r["id"].split(":", 1)[1].rsplit(".", 1)[0]),
                      nombre_contenedor(r["id"]))
        g.procs[f"{modulo}.{r['name']}".lower()] = Proc(
            id=r["id"], nombre=r["name"], modulo=modulo, archivo=r["file"] or "",
            linea_inicio=r["line_start"] or 0, linea_fin=r["line_end"] or 0)
    por_id = {p.id: p for p in g.procs.values()}

    for e in con.execute("SELECT * FROM edges"):
        p = por_id.get(e["src"])
        if e["kind"] == "HANDLES_EVENT" and p:
            p.evento = True
        elif e["kind"] == "EXECUTES_SQL" and p and e["dst"] in nodos:
            props = json.loads(nodos[e["dst"]]["props"] or "{}")
            p.sql.append({"texto": props.get("text", ""), "operacion": props.get("operation", ""), "linea": e["line"]})
            for e2 in con.execute("SELECT kind, dst FROM edges WHERE src = ?", (e["dst"],)):
                destino = (nodos[e2["dst"]]["name"] if e2["dst"] in nodos else e2["dst"])
                (p.lee if e2["kind"] == "READS" else p.escribe if e2["kind"] == "WRITES" else []).append(destino)
        elif e["kind"] == "CALLS" and p:
            if e["resolution"] == "unresolved":
                p.sin_resolver.append(f"{e['dst'].removeprefix('unresolved:')} ({p.archivo}:{e['line']})")
            elif e["dst"] in por_id:
                p.llama_a.append(por_id[e["dst"]].nombre)
    con.close()

    for fila in _csv(carpeta / "csv" / "procedimientos.csv"):
        if fila["id"] in por_id:
            por_id[fila["id"]].ciclomatica = int(fila.get("cyclomatic") or 1)
    for fila in _csv(carpeta / "csv" / "codigo_muerto.csv"):
        if fila["id"] in por_id:
            por_id[fila["id"]].muerto = True
            por_id[fila["id"]].seguro_borrar = fila.get("seguro_para_borrar", "").lower() in ("si", "sí", "true", "yes")
    g.formularios = _csv(carpeta / "csv" / "inventario.csv")
    g.tablas = _csv(carpeta / "csv" / "tablas.csv")
    g.riesgos = _csv(carpeta / "csv" / "riesgos.csv")
    g.paquetes_ssis = [{"id": r["id"], "nombre": r["name"], "archivo": r["file"]} for r in nodos.values() if r["kind"] == "ssis_pkg"]
    llamadas = [e for e in g.procs.values()]
    total = sum(len(p.llama_a) + len(p.sin_resolver) for p in llamadas)
    g.resolucion_llamadas = f"{total - sum(len(p.sin_resolver) for p in llamadas)}/{total}" if total else "—"
    return g


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] not in ("indexar", "resumen"):
        print(__doc__)
        return 2
    if argv[1] == "indexar":
        if not indexar(Path(argv[2]), Path(argv[3])):
            print("vb6graph no está instalado; se usa el grafo guardado si existe")
    g = cargar(Path(argv[-1]))
    if not g:
        print("Sin grafo")
        return 1
    print(f"procedimientos {len(g.procs)} (eventos {sum(p.evento for p in g.procs.values())}, "
          f"código muerto {len(g.muertos())}), paquetes SSIS {len(g.paquetes_ssis)}, llamadas entre procedimientos resueltas {g.resolucion_llamadas}")
    for p in g.muertos():
        print(f"  muerto: {p.modulo}.{p.nombre} ({p.evidencia}){' · seguro de borrar' if p.seguro_borrar else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

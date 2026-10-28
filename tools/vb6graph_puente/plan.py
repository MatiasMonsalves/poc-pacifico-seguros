"""Plan de migración y matriz de trazabilidad a partir del grafo de vb6graph.

Completa lo que la documentación de vb6graph marca como "propuesto — aún no implementado":
la matriz legado → nuevo → pruebas con estado por nodo y el % de avance. Cruza:
  * el grafo (reingenieria/vb6graph): formularios, procedimientos, paquetes SSIS, tablas,
    código muerto, dueños de lectura/escritura, riesgos, evidencia archivo:línea;
  * la transformación VB6 → .NET (transformacion/mapeo.json de vb62net);
  * la cobertura de la app terminada (transformacion/COBERTURA.md);
  * la conversión SSIS → ADF (adf/ y reingenieria/resumen.json);
  * las pruebas declaradas en sistema.json ("pruebas": {"<modulo>.<proc>": ["Clase de pruebas", ...]}).

Genera en sistemas/<id>/plan/:
  trazabilidad.csv   una fila por nodo legado relevante (plantilla de vb6graph 03_MIGRACION §4.5)
  olas.md            ola piloto con sus tareas y la propiedad de escritura de cada tabla
  ola-1/<ID>.md      una tarea por evento de formulario y por paquete SSIS (plantilla §4.3)
  AVANCE.md          % migrado por tipo de nodo

Uso:
    python plan.py <carpeta_del_sistema>
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grafo import cargar  # noqa: E402

TERMINADOS = ("hecho", "generado", "convertido", "reemplazado")


def cobertura(ruta: Path) -> dict[str, str]:
    """{'frmPolizas.cmdBuscar_Click': 'GET /api/...'} desde COBERTURA.md."""
    if not ruta.exists():
        return {}
    filas = re.findall(r"^\| `([\w.]+)` \|[^|]*\| `([^`]+)` \|", ruta.read_text(encoding="utf-8"), re.M)
    return dict(filas)


def slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")


def generar(carpeta: Path) -> dict:
    config = json.loads((carpeta / "sistema.json").read_text(encoding="utf-8"))
    sid = config["id"]
    g = cargar(carpeta / "reingenieria" / "vb6graph")
    if g is None:
        raise SystemExit(f"No hay grafo de vb6graph en {carpeta / 'reingenieria' / 'vb6graph'}")
    mapeo = {f"{m['modulo']}.{m['nombre']}".lower(): m for m in
             json.loads((carpeta / "transformacion" / "mapeo.json").read_text(encoding="utf-8"))} \
        if (carpeta / "transformacion" / "mapeo.json").exists() else {}
    app = cobertura(carpeta / "transformacion" / "COBERTURA.md")
    app_lower = {k.lower(): v for k, v in app.items()}
    resumen = json.loads((carpeta / "reingenieria" / "resumen.json").read_text(encoding="utf-8")) \
        if (carpeta / "reingenieria" / "resumen.json").exists() else {}
    sin_convertir = resumen.get("sin_convertir", [])
    pruebas = {k.lower(): v for k, v in config.get("pruebas", {}).items()}
    pipelines = {p.stem for p in (carpeta / "adf" / "pipeline").glob("*.json")}
    salida = carpeta / "plan"
    (salida / "ola-1").mkdir(parents=True, exist_ok=True)
    for viejo in (salida / "ola-1").glob("*.md"):
        viejo.unlink()

    filas, tareas = [], []
    prefijo = sid[:3].upper()

    # Formularios y módulos (tamaño del reporte de vb6graph)
    for f in g.formularios:
        filas.append({"legacy_node": f["id"], "tipo": f["kind"], "tamano": f.get("bucket", ""), "decision": "migrar",
                      "tarea": "", "componente_nuevo": "", "tests": "", "estado": "", "evidencia": f"{f['file']}:{f['line']}"})

    # Procedimientos
    n = 0
    for clave, p in sorted(g.procs.items(), key=lambda kv: (kv[1].archivo, kv[1].linea_inicio)):
        m = mapeo.get(clave, {})
        fila = {"legacy_node": p.id, "tipo": "proc", "tamano": "", "decision": "migrar", "tarea": "",
                "componente_nuevo": "", "tests": ";".join(pruebas.get(clave, [])), "estado": "", "evidencia": p.evidencia}
        if p.muerto:
            fila.update(decision="no migrar (código muerto)", estado="validar R3")
        elif clave in app_lower:
            fila.update(componente_nuevo=f"app: {app_lower[clave]}", estado="hecho")
        elif m.get("estado") == "Reemplazado":
            fila.update(decision="reemplazar", componente_nuevo=m.get("destino", ""), estado="reemplazado")
        elif m.get("estado") == "Automático":
            fila.update(componente_nuevo=f"generado: {m.get('destino', '')}", estado="generado")
        elif m.get("estado") in ("Parcial", "Pendiente"):
            fila.update(componente_nuevo=f"generado: {m.get('destino', '')}", estado=m["estado"].lower())
        else:
            fila["estado"] = "pendiente"
        if p.evento and not p.muerto:
            n += 1
            fila["tarea"] = f"{prefijo}-{n:02d}"
            if not fila["tests"] and fila["estado"] == "hecho":
                fila["tests"] = "scripts/demo (punta a punta);cobertura"
            tareas.append((fila["tarea"], p, m, fila))
        filas.append(fila)

    # Paquetes SSIS → pipelines de ADF
    for k, pkg in enumerate(g.paquetes_ssis, 1):
        pl = "PL_" + re.sub(r"\W", "_", pkg["nombre"])
        marcadores = [x for x in sin_convertir if x.startswith(pl + ":")]
        # Con marcadores (Script Task, Send Mail...) el paquete no cuenta como migrado
        estado = ("convertido" if not marcadores else f"parcial: {len(marcadores)} marcador(es) por migrar") if pl in pipelines else "pendiente"
        fila = {"legacy_node": pkg["id"], "tipo": "ssis_pkg", "tamano": "", "decision": "rediseño ADF",
                "tarea": f"ETL-{k:02d}", "componente_nuevo": f"adf/pipeline/{pl}.json" if pl in pipelines else "",
                "tests": "validar_adf;emulador ADF (scripts/demo)", "estado": estado, "evidencia": pkg["archivo"]}
        filas.append(fila)
        tareas.append((fila["tarea"], pkg, {"marcadores": marcadores, "pipeline": pl}, fila))

    # Tablas: dueños de escritura durante la coexistencia
    dueños: dict[str, dict[str, set[str]]] = {}
    for t in g.tablas:
        d = dueños.setdefault(t["table"], {"READS": set(), "WRITES": set()})
        d.setdefault(t["modo"], set()).add(f"{t['origen']}:{t['actor'].split('/')[-1]}")
    for tabla, d in sorted(dueños.items()):
        escritores = sorted(d.get("WRITES", set()))
        if tabla.startswith("db_proc:"):
            filas.append({"legacy_node": tabla, "tipo": "db_proc", "tamano": "", "decision": "se conserva en la BD (la invoca el sistema nuevo)",
                          "tarea": "", "componente_nuevo": "", "tests": "", "estado": "",
                          "evidencia": "ejecuta: " + ", ".join(sorted(d.get("EXEC", set())))})
            continue
        filas.append({"legacy_node": tabla, "tipo": "table", "tamano": "",
                      "decision": "coexistencia (misma BD)" if escritores else "solo lectura",
                      "tarea": "", "componente_nuevo": "", "tests": "", "estado": "",
                      "evidencia": "escribe: " + (", ".join(escritores) or "—") + " · lee: " + (", ".join(sorted(d.get("READS", set()))) or "—")})

    # Estado de formularios: hecho si todos sus eventos lo están
    for f in (x for x in filas if x["tipo"] in ("form", "module")):
        propios = [x for x in filas if x["tipo"] == "proc" and x["legacy_node"].startswith(f["legacy_node"].replace(f["tipo"] + ":", "proc:") + ".")
                   and not x["decision"].startswith("no migrar")]
        f["estado"] = "hecho" if propios and all(x["estado"] in TERMINADOS for x in propios) else ("en curso" if propios else "")
        if config.get("app") or (carpeta / "app").exists():
            f["componente_nuevo"] = "app terminada (sistemas/%s/app)" % sid if f["tipo"] == "form" else "dominio / infraestructura .NET 10"

    campos = ["legacy_node", "tipo", "tamano", "decision", "tarea", "componente_nuevo", "tests", "estado", "evidencia"]
    with open(salida / "trazabilidad.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)

    for tarea, origen, extra, fila in tareas:
        (salida / "ola-1" / f"{tarea}-{slug(getattr(origen, 'nombre', None) or origen['nombre'])}.md").write_text(
            tarea_md(tarea, origen, extra, fila, g, sid), encoding="utf-8")

    # Avance
    alcance = [x for x in filas if x["tipo"] in ("form", "module", "proc", "ssis_pkg") and not x["decision"].startswith("no migrar")]
    hechos = [x for x in alcance if x["estado"].split(" ")[0] in TERMINADOS]
    por_tipo = {}
    for x in alcance:
        t = por_tipo.setdefault(x["tipo"], [0, 0])
        t[1] += 1
        t[0] += x["estado"].split(" ")[0] in TERMINADOS
    avance = round(100 * len(hechos) / len(alcance)) if alcance else 0
    muertos = [x for x in filas if x["decision"].startswith("no migrar")]
    (salida / "AVANCE.md").write_text("\n".join([
        f"# Avance de la migración: {config['nombre']}", "",
        f"**{avance} %** de los nodos en alcance migrados ({len(hechos)} de {len(alcance)}). "
        f"Fuera de alcance por código muerto: {len(muertos)}.", "",
        "| Tipo | Migrados | En alcance |", "|---|---|---|",
        *[f"| {t} | {h} | {tot} |" for t, (h, tot) in por_tipo.items()], "",
        "Estados que cuentan como migrado: hecho (app terminada), generado (vb62net), convertido (ssis2adf), "
        "reemplazado (infraestructura .NET). Fuente: [trazabilidad.csv](trazabilidad.csv).", ""]), encoding="utf-8")

    (salida / "olas.md").write_text(olas_md(config, tareas, dueños, muertos), encoding="utf-8")
    return {"avance": avance, "hechos": len(hechos), "alcance": len(alcance), "tareas": len(tareas), "muertos": len(muertos)}


def tarea_md(tarea: str, origen, extra: dict, fila: dict, g, sid: str) -> str:
    if fila["tipo"] == "ssis_pkg":
        return "\n".join([
            f"# {tarea} {origen['nombre']} (SSIS → ADF)", "",
            f"- Épica: ETL · Estado: {fila['estado']}",
            f"- Paquete: `{origen['id']}` — `{origen['archivo']}` (vb6graph)",
            f"- Pipeline generado: `{fila['componente_nuevo'] or '—'}` (tools/ssis2adf)", "",
            "## Pendiente de migrar a mano", "",
            *([f"- {x}" for x in extra["marcadores"]] or ["- Nada: todas las tareas del paquete se convirtieron"]), "",
            "## Criterios de aceptación de paridad", "",
            "- Mismo archivo/origen de entrada → mismas filas en las tablas destino que el paquete SSIS.",
            "- Misma rama de error: la falla registra el error y deja el pipeline en Failed (actividad Fail).", "",
            "## Pruebas", "", f"- {fila['tests']}", ""])
    p = origen
    return "\n".join([
        f"# {tarea} {p.modulo}.{p.nombre}", "",
        f"- Épica: {p.modulo} (Ola 1) · Estado: {fila['estado']} · Complejidad ciclomática: {p.ciclomatica}",
        f"- Evidencia: `{p.id}` — `{p.evidencia}` (vb6graph)", "",
        "## Contexto en el legado", "",
        *([f"- SQL ({s['operacion']}) línea {s['linea']}: `{s['texto']}`" for s in p.sql] or ["- Sin SQL"]),
        *([f"- Llama a: {', '.join(p.llama_a)}"] if p.llama_a else []),
        *([f"- Llamada sin resolver (enlace tardío/COM): {x}" for x in p.sin_resolver]), "",
        "## Datos", "", "| Tabla | Modo |", "|---|---|",
        *[f"| {t} | READ |" for t in sorted(set(p.lee))], *[f"| {t} | WRITE |" for t in sorted(set(p.escribe))],
        *[f"| {t} | EXEC (procedimiento almacenado) |" for t in sorted(set(p.ejecuta))], "",
        "## Destino", "",
        f"- Generado por vb62net: `{extra.get('destino', '—')}` ({extra.get('estado', '—')})",
        f"- App terminada: {fila['componente_nuevo'] or 'pendiente'}", "",
        "## Criterios de aceptación de paridad", "",
        "- Mismos datos de entrada → mismo resultado que el VB6 (y que el componente COM, si aplica).",
        "- Mismas validaciones y mensajes de error equivalentes.", "",
        "## Pruebas", "", f"- {fila['tests'] or 'por definir'}", ""])


def olas_md(config: dict, tareas, dueños, muertos) -> str:
    out = [f"# Olas: {config['nombre']}", "",
           "Generado desde el grafo de vb6graph y los resultados de la fábrica. Alcance acotado de la POC: una ola piloto.", "",
           "## Ola 1 (piloto)", "", "| Tarea | Origen legado | Estado |", "|---|---|---|"]
    out += [f"| [{t}](ola-1/{t}-{slug(getattr(o, 'nombre', None) or o['nombre'])}.md) | `{f['legacy_node']}` | {f['estado']} |"
            for t, o, _, f in tareas]
    out += ["", "## Propiedad de escritura por tabla (coexistencia)", "", "| Tabla | Escribe hoy | Lee |", "|---|---|---|"]
    out += [f"| `{t}` | {', '.join(sorted(d.get('WRITES', set()))) or '—'} | {', '.join(sorted(d.get('READS', set()))) or '—'} |"
            for t, d in sorted(dueños.items())]
    out += ["", "## Fuera de alcance (código muerto, confirmar en R3)", ""]
    out += [f"- `{m['legacy_node']}` — {m['evidencia']}" for m in muertos] or ["- Nada"]
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    r = generar(Path(argv[1]))
    print(f"plan: {r['tareas']} tareas, avance {r['avance']} % ({r['hechos']}/{r['alcance']}), código muerto fuera de alcance: {r['muertos']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

"""Fábrica de migración para un portafolio de sistemas legados.

Cada sistema vive en sistemas/<id>/ con un sistema.json y sus fuentes en
sistemas/<id>/fuentes/ (paquetes SSIS, scripts T-SQL, proyectos VB6/.NET y
binarios). Para cada sistema este comando ejecuta:

  1. Inventario (tools/re_inventario)        → sistemas/<id>/reingenieria/inventario/
  2. REA sobre los binarios (tools/rea)       → sistemas/<id>/reingenieria/rea/
  3. Conversión SSIS → ADF (tools/ssis2adf)   → sistemas/<id>/adf/
  4. Resumen del sistema                       → sistemas/<id>/reingenieria/RESUMEN.md
y al final el consolidado del portafolio      → portafolio/PORTAFOLIO.md

Uso:
    python portafolio.py analizar [--solo <id>] [--decompilar] [--sin-rea]
    python portafolio.py nuevo <id> --nombre "Nombre del sistema"
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
for herramienta in ("re_inventario", "ssis2adf", "rea", "vb6graph_puente"):
    sys.path.insert(0, str(RAIZ / "tools" / herramienta))

from inventario import generar_markdown, inventariar  # noqa: E402
from ssis2adf import Opciones, convertir  # noqa: E402

SISTEMAS = RAIZ / "sistemas"
SALIDA_PORTAFOLIO = RAIZ / "portafolio"
PESO_ESFUERZO = {"Bajo": 2, "Medio": 5, "Alto": 10}


def cargar(carpeta: Path) -> dict:
    config = json.loads((carpeta / "sistema.json").read_text(encoding="utf-8"))
    config.setdefault("id", carpeta.name)
    config.setdefault("nombre", carpeta.name)
    config.setdefault("fuentes", "fuentes")
    config.setdefault("adf", {})
    return config


def analizar_sistema(carpeta: Path, decompilar: bool, con_rea: bool) -> dict:
    config = cargar(carpeta)
    fuentes = carpeta / config["fuentes"]
    reing = carpeta / "reingenieria"
    print(f"\n== {config['id']}: {config['nombre']}")

    # 1. Inventario
    inv = inventariar(fuentes)
    (reing / "inventario").mkdir(parents=True, exist_ok=True)
    (reing / "inventario" / "inventario.json").write_text(json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8")
    (reing / "inventario" / "inventario.md").write_text(generar_markdown(inv), encoding="utf-8")
    print(f"   inventario: {inv['resumen']}")

    # 1b. Grafo de conocimiento con vb6graph (assessment: linaje VB6↔SSIS, riesgos, código muerto)
    from grafo import cargar as cargar_grafo, indexar as indexar_grafo
    if indexar_grafo(fuentes, reing / "vb6graph"):
        print("   vb6graph: grafo y reporte actualizados")
    g = cargar_grafo(reing / "vb6graph")
    if g:
        print(f"   vb6graph: {len(g.procs)} procedimientos, {len(g.muertos())} código muerto, {len(g.paquetes_ssis)} paquetes SSIS")
    else:
        print("   vb6graph: no instalado y sin grafo guardado (opcional; ver docs/VB6GRAPH.md)")

    # 2. REA sobre binarios
    binarios = []
    rutas_bin = [carpeta / r for r in config.get("binarios", [])] or [fuentes]
    if con_rea and shutil.which("rea"):
        from analizar_binarios import analizar_todos
        binarios = analizar_todos(rutas_bin, reing / "rea", decompilar)
        print(f"   REA: {len(binarios)} binario(s)")
    elif con_rea:
        print("   REA: no instalado (npm install -g rea-agents); se omiten los binarios")
    if not binarios and (reing / "rea" / "binarios.json").exists():
        binarios = json.loads((reing / "rea" / "binarios.json").read_text(encoding="utf-8"))
        print(f"   REA: se reutiliza el análisis anterior ({len(binarios)} binario(s))")

    # 3. SSIS → ADF
    conversion = {"pipelines": [], "secretos": []}
    if any(fuentes.rglob("*.dtsx")):
        a = config["adf"]
        opciones = Opciones(
            prefijo_secretos=a.get("prefijoSecretos", config["id"]),
            contenedor_blob=a.get("contenedorBlob", "entrada"),
            zona_horaria=a.get("zonaHoraria", "Pacific SA Standard Time"),
            key_vault_url=a.get("keyVaultUrl", "https://kv-pacifico-poc.vault.azure.net/"),
        )
        destino = carpeta / "adf"
        for sub in ("pipeline", "dataset", "linkedService"):
            shutil.rmtree(destino / sub, ignore_errors=True)
        conversion = convertir([fuentes], [fuentes], destino, opciones)
        print(f"   ADF: {len(conversion['pipelines'])} pipeline(s)")

    resumen = resumir(config, inv, binarios, conversion)
    (reing / "RESUMEN.md").write_text(resumen_md(resumen), encoding="utf-8")
    return resumen


def bases_de_datos(inv: dict) -> list[str]:
    cadenas = [c["connection_string"] for p in inv["paquetes_ssis"] for c in p["conexiones"]]
    cadenas += [c for a in inv["archivos_codigo"] for c in a["conexiones"]]
    return sorted({m.group(1) for c in cadenas for m in [re.search(r"(?i)(?:Initial Catalog|Database)\s*=\s*([^;]+)", c)] if m})


def resumir(config: dict, inv: dict, binarios: list[dict], conversion: dict) -> dict:
    r = inv["resumen"]
    riesgos = [f"{p['archivo']}: {x}" for p in inv["proyectos"] for x in p["riesgos"]]
    advertencias = [f"{p['pipeline']}: {a}" for p in conversion["pipelines"] for a in p["advertencias"]]
    sin_convertir = [f"{p['pipeline']}: {t}" for p in conversion["pipelines"] for t in p["no_convertidas"]]
    nativos = [b for b in binarios if not str(b.get("tipo", "")).startswith(".NET")]
    sql_en_binarios = sum(len(b.get("sql", [])) for b in binarios)

    # Puntaje relativo para ordenar el portafolio (no es una estimación de horas)
    puntaje = (r["tareas_ssis"] + 3 * len(sin_convertir) + len(advertencias) * 0.5
               + r["objetos_bd"] * 0.5
               + sum(PESO_ESFUERZO.get(p["esfuerzo"], 5) for p in inv["proyectos"])
               + 3 * (len(binarios) - len(nativos)) + 8 * len(nativos)
               + len(riesgos))
    nivel = "Baja" if puntaje < 20 else "Media" if puntaje < 45 else "Alta"
    return {
        "id": config["id"], "nombre": config["nombre"], "descripcion": config.get("descripcion", ""),
        "criticidad": config.get("criticidad", "—"), "estado": config.get("estado", "Analizado"),
        "tecnologias": sorted({p["plataforma"] if p["plataforma"] != ".NET Framework" else f".NET Framework {p['framework']}"
                               for p in inv["proyectos"]} | ({"SSIS"} if r["paquetes_ssis"] else set())
                              | ({"T-SQL"} if r["objetos_bd"] else set())),
        "metricas": {**r, "binarios": len(binarios), "binarios_nativos": len(nativos),
                     "sql_en_binarios": sql_en_binarios, "pipelines": len(conversion["pipelines"]),
                     "actividades_sin_convertir": len(sin_convertir), "advertencias_adf": len(advertencias)},
        "bases_de_datos": bases_de_datos(inv),
        "proyectos": [{k: p[k] for k in ("archivo", "tipo_aplicacion", "framework", "esfuerzo", "ruta_sugerida")}
                      for p in inv["proyectos"]],
        "binarios": [{k: b.get(k) for k in ("binario", "tipo", "framework", "siguiente_paso")} for b in binarios],
        "riesgos": riesgos, "sin_convertir": sin_convertir, "advertencias_adf": advertencias,
        "secretos": conversion.get("secretos", []),
        "puntaje": round(puntaje, 1), "complejidad": nivel,
    }


def resumen_md(s: dict) -> str:
    m = s["metricas"]
    out = [f"# {s['nombre']} (`{s['id']}`)", "", s["descripcion"], "",
           f"**Complejidad: {s['complejidad']}** (puntaje {s['puntaje']}) · Criticidad: {s['criticidad']} · Estado: {s['estado']}", "",
           f"Tecnologías: {', '.join(s['tecnologias']) or '—'} · BDs: {', '.join(s['bases_de_datos']) or '—'}", "",
           "| Métrica | Valor |", "|---|---|",
           f"| Paquetes SSIS / tareas | {m['paquetes_ssis']} / {m['tareas_ssis']} |",
           f"| Pipelines ADF generados | {m['pipelines']} ({m['actividades_sin_convertir']} actividades sin convertir, {m['advertencias_adf']} advertencias) |",
           f"| Objetos de BD | {m['objetos_bd']} |",
           f"| Proyectos VB6/.NET | {m['proyectos']} |",
           f"| Binarios analizados con REA | {m['binarios']} ({m['binarios_nativos']} nativos/VB6) |", ""]
    if s["proyectos"]:
        out += ["## Proyectos", "", "| Proyecto | Tipo | Framework | Esfuerzo | Ruta sugerida |", "|---|---|---|---|---|"]
        out += [f"| `{p['archivo']}` | {p['tipo_aplicacion']} | {p['framework']} | {p['esfuerzo']} | {p['ruta_sugerida']} |" for p in s["proyectos"]]
        out.append("")
    if s["binarios"]:
        out += ["## Binarios", "", "| Binario | Tipo | Siguiente paso |", "|---|---|---|"]
        out += [f"| `{b['binario']}` | {b['tipo']} {b.get('framework') or ''} | {b['siguiente_paso']} |" for b in s["binarios"]]
        out.append("")
    for titulo, clave in (("Actividades ADF sin conversión automática", "sin_convertir"), ("Riesgos", "riesgos"),
                          ("Advertencias de la conversión a ADF", "advertencias_adf")):
        if s[clave]:
            out += [f"## {titulo}", "", *[f"- {x}" for x in s[clave]], ""]
    out += ["## Detalle", "", "- [Inventario](inventario/inventario.md)",
            "- [Binarios (REA)](rea/BINARIOS.md)" if s["binarios"] else "",
            "- [Conversión a ADF](../adf/REPORTE_CONVERSION.md)" if s["metricas"]["pipelines"] else "", ""]
    return "\n".join(l for l in out if l is not None)


def portafolio_md(resumenes: list[dict]) -> str:
    orden = sorted(resumenes, key=lambda s: s["puntaje"])
    out = ["# Portafolio de sistemas legados", "", f"Generado el {date.today():%d-%m-%Y} con `tools/portafolio`.", "",
           "| Sistema | Tecnologías | Paquetes SSIS | Proyectos | Binarios | Sin convertir | Riesgos | Complejidad |",
           "|---|---|---|---|---|---|---|---|"]
    for s in orden:
        m = s["metricas"]
        out.append(f"| [{s['nombre']}](../sistemas/{s['id']}/reingenieria/RESUMEN.md) | {', '.join(s['tecnologias'])} | "
                   f"{m['paquetes_ssis']} | {m['proyectos']} | {m['binarios']} | {m['actividades_sin_convertir']} | "
                   f"{len(s['riesgos'])} | {s['complejidad']} ({s['puntaje']}) |")

    # BDs compartidas entre sistemas: acoplamiento que obliga a migrar juntos o a coordinar
    uso: dict[str, list[str]] = {}
    for s in resumenes:
        for bd in s["bases_de_datos"]:
            uso.setdefault(bd, []).append(s["id"])
    compartidas = {bd: ids for bd, ids in uso.items() if len(ids) > 1}

    out += ["", "## Orden sugerido", "",
            "De menor a mayor complejidad: los primeros sistemas sirven para ajustar la fábrica (convertidor, emulador, "
            "pruebas de paridad) antes de abordar los más riesgosos. La criticidad de negocio puede cambiar este orden.", ""]
    out += [f"{i}. **{s['nombre']}**: {s['complejidad'].lower()}"
            + (f"; atención: {s['sin_convertir'][0]}" if s["sin_convertir"] else "") for i, s in enumerate(orden, 1)]
    out += ["", "## Bases de datos compartidas", ""]
    out += [f"- `{bd}`: {', '.join(ids)}" for bd, ids in compartidas.items()] or ["- Ninguna detectada en las cadenas de conexión"]
    out += ["", "## Riesgos transversales", ""]
    contador: dict[str, int] = {}
    for s in resumenes:
        for riesgo in {r.split(": ", 1)[-1] for r in s["riesgos"]}:
            contador[riesgo] = contador.get(riesgo, 0) + 1
    out += [f"- ({n} sistema{'s' if n > 1 else ''}) {r}" for r, n in sorted(contador.items(), key=lambda x: -x[1])] or ["- Ninguno"]
    return "\n".join(out) + "\n"


def nuevo(id_sistema: str, nombre: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,40}", id_sistema):
        raise SystemExit("El id debe tener minúsculas, números y guiones (se usa como nombre de factoría ADF y prefijo de secretos)")
    carpeta = SISTEMAS / id_sistema
    if carpeta.exists():
        raise SystemExit(f"Ya existe {carpeta}")
    for sub in ("fuentes/db", "fuentes/ssis", "fuentes/vb6", "fuentes/dotnet", "fuentes/bin", "datos/blob/entrada"):
        (carpeta / sub).mkdir(parents=True)
        (carpeta / sub / ".gitkeep").touch()
    (carpeta / "sistema.json").write_text(json.dumps({
        "id": id_sistema, "nombre": nombre, "descripcion": "", "criticidad": "Media", "estado": "Fuentes pendientes",
        "binarios": ["fuentes/bin"],
        "adf": {"prefijoSecretos": id_sistema, "contenedorBlob": "entrada", "zonaHoraria": "Pacific SA Standard Time"},
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Creado {carpeta}. Copie los fuentes en fuentes/ (db, ssis, vb6, dotnet, bin) y ejecute: "
          f"python tools/portafolio/portafolio.py analizar --solo {id_sistema}")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="comando", required=True)
    a = sub.add_parser("analizar")
    a.add_argument("--solo")
    a.add_argument("--decompilar", action="store_true", help="decompila los assemblies .NET con ILSpy (Docker)")
    a.add_argument("--sin-rea", action="store_true")
    n = sub.add_parser("nuevo")
    n.add_argument("id")
    n.add_argument("--nombre", required=True)
    args = p.parse_args(argv[1:])

    if args.comando == "nuevo":
        nuevo(args.id, args.nombre)
        return 0

    carpetas = sorted(c for c in SISTEMAS.iterdir() if (c / "sistema.json").exists())
    if args.solo:
        carpetas = [c for c in carpetas if c.name == args.solo] or sys.exit(f"No existe sistemas/{args.solo}/sistema.json")
    for c in carpetas:
        resumen = analizar_sistema(c, args.decompilar, not args.sin_rea)
        (c / "reingenieria" / "resumen.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")

    # El consolidado usa el último resumen de todos los sistemas, aunque se haya analizado solo uno
    resumenes = [json.loads((c / "reingenieria" / "resumen.json").read_text(encoding="utf-8"))
                 for c in sorted(SISTEMAS.iterdir()) if (c / "reingenieria" / "resumen.json").exists()]
    SALIDA_PORTAFOLIO.mkdir(exist_ok=True)
    (SALIDA_PORTAFOLIO / "portafolio.json").write_text(json.dumps(resumenes, indent=2, ensure_ascii=False), encoding="utf-8")
    (SALIDA_PORTAFOLIO / "PORTAFOLIO.md").write_text(portafolio_md(resumenes), encoding="utf-8")
    print(f"\nPortafolio: {SALIDA_PORTAFOLIO / 'PORTAFOLIO.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

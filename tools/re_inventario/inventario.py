"""Inventario automático para ingeniería inversa de un sistema legado.

Recorre una carpeta con los fuentes del sistema y extrae:
  * Paquetes SSIS (.dtsx): conexiones, variables, tareas, flujo de control,
    componentes de data flow y SQL embebido.
  * T-SQL (.sql): objetos definidos (procedimientos, funciones, vistas,
    tablas, triggers) y objetos referenciados (tablas leídas/escritas, EXEC).
  * VB6 (.vbp/.frm/.bas/.cls) y .NET (.vb/.cs/.config): cadenas de conexión,
    SQL embebido y llamadas a procedimientos.

Salida: inventario.json (para procesar) e inventario.md (para leer), con un
diagrama Mermaid del flujo de control de cada paquete SSIS.

Uso:
    python inventario.py <carpeta_fuentes> <carpeta_salida>

Solo usa la librería estándar de Python (3.9+).
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

NS_DTS = "www.microsoft.com/SqlServer/Dts"
NS_SQLTASK = "www.microsoft.com/sqlserver/dts/tasks/sqltask"


def dts(attr: str) -> str:
    return f"{{{NS_DTS}}}{attr}"


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------


@dataclass
class TareaSSIS:
    ref_id: str
    nombre: str
    tipo: str
    sql: str = ""
    conexion: str = ""
    componentes: list[dict] = field(default_factory=list)


@dataclass
class PaqueteSSIS:
    archivo: str
    nombre: str
    conexiones: list[dict] = field(default_factory=list)
    variables: list[dict] = field(default_factory=list)
    tareas: list[TareaSSIS] = field(default_factory=list)
    precedencias: list[dict] = field(default_factory=list)


@dataclass
class ArchivoSQL:
    archivo: str
    objetos_definidos: list[dict] = field(default_factory=list)
    lee: list[str] = field(default_factory=list)
    escribe: list[str] = field(default_factory=list)
    ejecuta: list[str] = field(default_factory=list)


@dataclass
class ArchivoCodigo:
    archivo: str
    lenguaje: str
    conexiones: list[str] = field(default_factory=list)
    sql_embebido: list[str] = field(default_factory=list)
    procedimientos_llamados: list[str] = field(default_factory=list)
    componentes_com: list[str] = field(default_factory=list)
    procesos_externos: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SSIS
# ---------------------------------------------------------------------------

# Nombres legibles para los CreationName/ExecutableType más comunes.
TIPOS_TAREA = {
    "Microsoft.ExecuteSQLTask": "Execute SQL",
    "Microsoft.Pipeline": "Data Flow",
    "Microsoft.ExecutePackageTask": "Execute Package",
    "Microsoft.FileSystemTask": "File System",
    "Microsoft.ScriptTask": "Script Task",
    "Microsoft.SendMailTask": "Send Mail",
    "Microsoft.FtpTask": "FTP",
    "STOCK:SEQUENCE": "Sequence Container",
    "STOCK:FORLOOP": "For Loop",
    "STOCK:FOREACHLOOP": "Foreach Loop",
}


def _tipo_legible(executable_type: str) -> str:
    for clave, legible in TIPOS_TAREA.items():
        if executable_type.startswith(clave) or clave in executable_type:
            return legible
    return executable_type


def _propiedad(componente: ET.Element, nombre: str) -> str:
    for prop in componente.iter("property"):
        if prop.get("name") == nombre and prop.text:
            return prop.text.strip()
    return ""


def _componentes_data_flow(executable: ET.Element) -> list[dict]:
    componentes = []
    for comp in executable.iter("component"):
        info = {
            "nombre": comp.get("name", ""),
            "clase": comp.get("componentClassID", ""),
        }
        for prop in ("SqlCommand", "OpenRowset", "TableOrViewName"):
            valor = _propiedad(comp, prop)
            if valor:
                info[prop] = valor
        conn = comp.find("connections/connection")
        if conn is not None:
            info["conexion"] = conn.get("connectionManagerRefId", "")
        componentes.append(info)
    return componentes


def analizar_dtsx(ruta: Path, base: Path) -> PaqueteSSIS:
    raiz = ET.parse(ruta).getroot()
    paquete = PaqueteSSIS(
        archivo=str(ruta.relative_to(base)),
        nombre=raiz.get(dts("ObjectName"), ruta.stem),
    )

    for cm in raiz.iter(dts("ConnectionManager")):
        conn_str = ""
        inner = cm.find(f"{dts('ObjectData')}/{dts('ConnectionManager')}")
        if inner is not None:
            conn_str = inner.get(dts("ConnectionString"), "")
        if cm.get(dts("ObjectName")):
            paquete.conexiones.append(
                {
                    "nombre": cm.get(dts("ObjectName")),
                    "tipo": cm.get(dts("CreationName"), ""),
                    "ref_id": cm.get(dts("refId"), ""),
                    "connection_string": _ocultar_password(conn_str),
                }
            )

    for var in raiz.iter(dts("Variable")):
        valor = var.find(dts("VariableValue"))
        paquete.variables.append(
            {
                "nombre": f"{var.get(dts('Namespace'), 'User')}::{var.get(dts('ObjectName'), '')}",
                "expresion": var.get(dts("Expression"), ""),
                "valor": (valor.text or "") if valor is not None else "",
            }
        )

    for ex in raiz.iter(dts("Executable")):
        if ex is raiz:
            continue
        tipo = ex.get(dts("ExecutableType"), "")
        tarea = TareaSSIS(
            ref_id=ex.get(dts("refId"), ""),
            nombre=ex.get(dts("ObjectName"), ""),
            tipo=_tipo_legible(tipo),
        )
        sql_task = ex.find(f"{dts('ObjectData')}/{{{NS_SQLTASK}}}SqlTaskData")
        if sql_task is not None:
            tarea.sql = sql_task.get(f"{{{NS_SQLTASK}}}SqlStatementSource", "").strip()
            tarea.conexion = sql_task.get(f"{{{NS_SQLTASK}}}Connection", "")
        if tarea.tipo == "Data Flow":
            tarea.componentes = _componentes_data_flow(ex)
        paquete.tareas.append(tarea)

    for pc in raiz.iter(dts("PrecedenceConstraint")):
        valor = pc.get(dts("Value"), "0")
        paquete.precedencias.append(
            {
                "desde": pc.get(dts("From"), ""),
                "hacia": pc.get(dts("To"), ""),
                "condicion": {"0": "Success", "1": "Failure", "2": "Completion"}.get(valor, valor),
                "expresion": pc.get(dts("Expression"), ""),
            }
        )
    return paquete


def _ocultar_password(conn_str: str) -> str:
    return re.sub(r"(?i)(password|pwd)\s*=\s*[^;]*", r"\1=****", conn_str)


# ---------------------------------------------------------------------------
# T-SQL
# ---------------------------------------------------------------------------

_IDENT = r"((?:\[[^\]]+\]|[A-Za-z_#@][\w#@$]*)(?:\s*\.\s*(?:\[[^\]]+\]|[A-Za-z_#@][\w#@$]*)){0,3})"

RE_DEFINE = re.compile(
    r"\b(?:CREATE|ALTER)\s+(?:OR\s+ALTER\s+)?(PROC(?:EDURE)?|FUNCTION|VIEW|TABLE|TRIGGER)\s+" + _IDENT,
    re.IGNORECASE,
)
RE_LEE = re.compile(r"\b(?:FROM|JOIN)\s+" + _IDENT, re.IGNORECASE)
RE_ESCRIBE = re.compile(
    r"\b(?:INSERT\s+(?:INTO\s+)?|UPDATE\s+|DELETE\s+(?:FROM\s+)?|MERGE\s+(?:INTO\s+)?|TRUNCATE\s+TABLE\s+|SELECT\s+.+?\s+INTO\s+)" + _IDENT,
    re.IGNORECASE,
)
RE_EXEC = re.compile(r"\bEXEC(?:UTE)?\s+(?:@\w+\s*=\s*)?" + _IDENT, re.IGNORECASE)

PALABRAS_NO_OBJETO = {"select", "where", "set", "values", "(", "dbo", "sp_executesql"}


def _quitar_comentarios(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def _normalizar(nombre: str) -> str:
    return re.sub(r"\s+", "", nombre).replace("[", "").replace("]", "")


def _unicos(nombres) -> list[str]:
    vistos = {}
    for n in nombres:
        n = _normalizar(n)
        if n and not n.startswith("@") and n.lower() not in PALABRAS_NO_OBJETO:
            vistos.setdefault(n.lower(), n)
    return sorted(vistos.values(), key=str.lower)


def analizar_tsql(texto: str) -> dict:
    limpio = _quitar_comentarios(texto)
    definidos = [
        {"tipo": m.group(1).upper().replace("PROCEDURE", "PROC"), "nombre": _normalizar(m.group(2))}
        for m in RE_DEFINE.finditer(limpio)
    ]
    return {
        "objetos_definidos": definidos,
        "lee": _unicos(m.group(1) for m in RE_LEE.finditer(limpio)),
        "escribe": _unicos(m.group(1) for m in RE_ESCRIBE.finditer(limpio)),
        "ejecuta": _unicos(m.group(1) for m in RE_EXEC.finditer(limpio)),
    }


def analizar_sql(ruta: Path, base: Path) -> ArchivoSQL:
    texto = _leer_texto(ruta)
    return ArchivoSQL(archivo=str(ruta.relative_to(base)), **analizar_tsql(texto))


# ---------------------------------------------------------------------------
# VB6 / .NET
# ---------------------------------------------------------------------------

EXT_CODIGO = {
    ".vbp": "VB6", ".frm": "VB6", ".bas": "VB6", ".cls": "VB6", ".ctl": "VB6",
    ".vb": "VB.NET", ".cs": "C#", ".config": ".NET config",
}

RE_CONN = re.compile(
    r"""["']([^"']*(?:Provider|Data Source|Server|Initial Catalog|DSN)\s*=[^"']*)["']""",
    re.IGNORECASE,
)
RE_SQL_STR = re.compile(
    r"""["']\s*((?:SELECT|INSERT|UPDATE|DELETE|EXEC|EXECUTE|MERGE|TRUNCATE)\b[^"']*)["']""",
    re.IGNORECASE,
)
# CommandText = "sp_x" / New SqlCommand("sp_x") / .Execute "sp_x" con CommandType de procedimiento
RE_PROC = re.compile(
    r"""(?:CommandText\s*=\s*|SqlCommand\(\s*|\.Execute\s*\(?\s*)["']((?:\[?\w+\]?\.)?\[?(?:usp|sp|pr|proc)_?\w*\]?)["']""",
    re.IGNORECASE,
)

# CreateObject("Prog.Id") / New Prog.Id en VB6
RE_COM = re.compile(r"""CreateObject\(\s*["']([\w.]+)["']""", re.IGNORECASE)
# Shell / Process.Start: ejecutables invocados (dtexec = paquetes SSIS)
RE_PROCESO = re.compile(r"\b(?:Shell|Process\.Start)\b[^\n]*", re.IGNORECASE)
RE_EXE = re.compile(r"([\w\\:. ]+?\.(?:exe|dtsx|bat|cmd))", re.IGNORECASE)


def analizar_codigo(ruta: Path, base: Path) -> ArchivoCodigo:
    texto = _leer_texto(ruta)
    # VB6/VB.NET concatenan SQL con & y _ ; se unen las líneas continuadas.
    unido = re.sub(r'"\s*&\s*_?\s*\n\s*"', "", texto)
    return ArchivoCodigo(
        archivo=str(ruta.relative_to(base)),
        lenguaje=EXT_CODIGO[ruta.suffix.lower()],
        conexiones=sorted({_ocultar_password(m.group(1)) for m in RE_CONN.finditer(unido)}),
        sql_embebido=list(dict.fromkeys(m.group(1).strip() for m in RE_SQL_STR.finditer(unido))),
        procedimientos_llamados=sorted({m.group(1) for m in RE_PROC.finditer(unido)}),
        componentes_com=sorted({m.group(1) for m in RE_COM.finditer(unido)}),
        procesos_externos=_procesos_externos(unido),
    )


def _procesos_externos(texto: str) -> list[str]:
    # Las rutas suelen estar en constantes: se resuelven RUTA = "..." del mismo archivo.
    constantes = dict(re.findall(r'(?i)Const\s+(\w+)\s+As\s+String\s*=\s*"([^"]*)"', texto))
    procesos = []
    for m in RE_PROCESO.finditer(texto):
        linea = m.group(0)
        for nombre, valor in constantes.items():
            linea = linea.replace(nombre, valor)
        procesos.append(linea.strip())
    # Constantes con ejecutables aunque la llamada esté en otro archivo
    procesos += [f"{n} = {v}" for n, v in constantes.items() if RE_EXE.search(v)]
    return list(dict.fromkeys(procesos))


def _leer_texto(ruta: Path) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return ruta.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ruta.read_text(encoding="latin-1", errors="replace")


# ---------------------------------------------------------------------------
# Reporte
# ---------------------------------------------------------------------------


def _id_mermaid(ref_id: str) -> str:
    return "n" + re.sub(r"\W", "_", ref_id)


def diagrama_paquete(p: PaqueteSSIS) -> str:
    lineas = ["flowchart TD"]
    for t in p.tareas:
        etiqueta = f"{t.nombre}<br/><i>{t.tipo}</i>".replace('"', "'")
        lineas.append(f'    {_id_mermaid(t.ref_id)}["{etiqueta}"]')
    for pc in p.precedencias:
        flecha = {"Success": "-->", "Failure": "-.->|Failure|", "Completion": "==>"}.get(pc["condicion"], "-->")
        lineas.append(f"    {_id_mermaid(pc['desde'])} {flecha} {_id_mermaid(pc['hacia'])}")
    return "\n".join(lineas)


def _lista(items) -> str:
    return ", ".join(f"`{i}`" for i in items) if items else "—"


def generar_markdown(inv: dict) -> str:
    out = ["# Inventario de ingeniería inversa", ""]
    r = inv["resumen"]
    out += [
        "| Elemento | Cantidad |", "|---|---|",
        f"| Paquetes SSIS | {r['paquetes_ssis']} |",
        f"| Tareas SSIS | {r['tareas_ssis']} |",
        f"| Archivos T-SQL | {r['archivos_sql']} |",
        f"| Objetos de BD definidos | {r['objetos_bd']} |",
        f"| Archivos VB6/.NET | {r['archivos_codigo']} |",
        "",
    ]

    out.append("## Paquetes SSIS\n")
    for p in inv["paquetes_ssis"]:
        out += [f"### {p['nombre']}  (`{p['archivo']}`)", "", "**Conexiones**", ""]
        out += [f"- `{c['nombre']}` ({c['tipo']}): `{c['connection_string']}`" for c in p["conexiones"]] or ["- —"]
        if p["variables"]:
            out += ["", "**Variables**", ""]
            out += [f"- `{v['nombre']}` = `{v['expresion'] or v['valor']}`" for v in p["variables"]]
        out += ["", "**Flujo de control**", "", "```mermaid", diagrama_paquete(PaqueteSSIS(
            archivo=p["archivo"], nombre=p["nombre"],
            tareas=[TareaSSIS(**t) for t in p["tareas"]], precedencias=p["precedencias"],
        )), "```", "", "**Tareas**", ""]
        for t in p["tareas"]:
            out.append(f"- **{t['nombre']}** — {t['tipo']}")
            if t["sql"]:
                out += ["  ```sql", *("  " + l for l in t["sql"].splitlines()), "  ```"]
            for c in t["componentes"]:
                extra = c.get("SqlCommand") or c.get("OpenRowset") or c.get("TableOrViewName") or ""
                out.append(f"  - {c['nombre']} `{c['clase']}` {('→ `' + extra + '`') if extra else ''}")
        out.append("")

    out.append("## Objetos T-SQL\n")
    out += ["| Archivo | Define | Lee | Escribe | Ejecuta |", "|---|---|---|---|---|"]
    for s in inv["archivos_sql"]:
        define = ", ".join(f"{o['tipo']} `{o['nombre']}`" for o in s["objetos_definidos"]) or "—"
        out.append(f"| `{s['archivo']}` | {define} | {_lista(s['lee'])} | {_lista(s['escribe'])} | {_lista(s['ejecuta'])} |")
    out.append("")

    out.append("## Aplicación VB6 / .NET\n")
    for c in inv["archivos_codigo"]:
        out += [f"### `{c['archivo']}` ({c['lenguaje']})", ""]
        out.append(f"- Conexiones: {_lista(c['conexiones'])}")
        out.append(f"- Procedimientos llamados: {_lista(c['procedimientos_llamados'])}")
        if c["componentes_com"]:
            out.append(f"- Componentes COM: {_lista(c['componentes_com'])}")
        if c["procesos_externos"]:
            out.append("- Procesos externos:")
            out += [f"  - `{p}`" for p in c["procesos_externos"]]
        if c["sql_embebido"]:
            out.append("- SQL embebido:")
            out += [f"  - `{q}`" for q in c["sql_embebido"]]
        out.append("")

    out.append("## Matriz de dependencias (objeto → quién lo usa)\n")
    out += ["| Objeto | Usado por |", "|---|---|"]
    for obj, usuarios in sorted(inv["dependencias"].items(), key=lambda kv: kv[0].lower()):
        out.append(f"| `{obj}` | {', '.join(sorted(set(usuarios)))} |")
    out.append("")
    return "\n".join(out)


def _dependencias(paquetes, sqls, codigos) -> dict[str, list[str]]:
    deps: dict[str, list[str]] = {}

    def agregar(objetos, usuario):
        for o in objetos:
            deps.setdefault(_normalizar(o), []).append(usuario)

    for p in paquetes:
        for t in p.tareas:
            textos = [t.sql] + [c.get("SqlCommand", "") for c in t.componentes]
            for texto in filter(None, textos):
                a = analizar_tsql(texto)
                agregar(a["lee"] + a["escribe"] + a["ejecuta"], f"SSIS:{p.nombre}/{t.nombre}")
            agregar([c["OpenRowset"] for c in t.componentes if c.get("OpenRowset")], f"SSIS:{p.nombre}/{t.nombre}")
    for s in sqls:
        definidos = ", ".join(o["nombre"] for o in s.objetos_definidos) or s.archivo
        agregar(s.lee + s.escribe + s.ejecuta, f"SQL:{definidos}")
    for c in codigos:
        agregar(c.procedimientos_llamados, f"APP:{c.archivo}")
        agregar([f"COM:{p}" for p in c.componentes_com], f"APP:{c.archivo}")
        for q in c.sql_embebido:
            a = analizar_tsql(q)
            agregar(a["lee"] + a["escribe"] + a["ejecuta"], f"APP:{c.archivo}")
    return deps


def inventariar(fuentes: Path) -> dict:
    paquetes, sqls, codigos, errores = [], [], [], []
    for ruta in sorted(p for p in fuentes.rglob("*") if p.is_file()):
        ext = ruta.suffix.lower()
        try:
            if ext == ".dtsx":
                paquetes.append(analizar_dtsx(ruta, fuentes))
            elif ext == ".sql":
                sqls.append(analizar_sql(ruta, fuentes))
            elif ext in EXT_CODIGO:
                codigos.append(analizar_codigo(ruta, fuentes))
        except (ET.ParseError, OSError) as e:
            errores.append({"archivo": str(ruta.relative_to(fuentes)), "error": str(e)})

    return {
        "resumen": {
            "paquetes_ssis": len(paquetes),
            "tareas_ssis": sum(len(p.tareas) for p in paquetes),
            "archivos_sql": len(sqls),
            "objetos_bd": sum(len(s.objetos_definidos) for s in sqls),
            "archivos_codigo": len(codigos),
        },
        "paquetes_ssis": [asdict(p) for p in paquetes],
        "archivos_sql": [asdict(s) for s in sqls],
        "archivos_codigo": [asdict(c) for c in codigos],
        "dependencias": _dependencias(paquetes, sqls, codigos),
        "errores": errores,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    fuentes, salida = Path(argv[1]).resolve(), Path(argv[2])
    salida.mkdir(parents=True, exist_ok=True)
    inv = inventariar(fuentes)
    (salida / "inventario.json").write_text(json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8")
    (salida / "inventario.md").write_text(generar_markdown(inv), encoding="utf-8")
    print(json.dumps(inv["resumen"], ensure_ascii=False))
    for e in inv["errores"]:
        print(f"ERROR {e['archivo']}: {e['error']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

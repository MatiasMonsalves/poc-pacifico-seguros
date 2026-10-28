"""Transformación de un proyecto VB6 a un proyecto .NET 10 (API mínima de ASP.NET Core).

Lee el .vbp y sus formularios/módulos y genera:
  * <salida>/<Proyecto>.Generado/  proyecto .NET 10 que compila:
      - un endpoint por cada evento de formulario (cmdX_Click, Form_Load...)
      - SQL concatenado → consulta parametrizada
      - ADO con procedimiento almacenado → llamada parametrizada
      - Shell dtexec <paquete>.dtsx → ejecución del pipeline PL_<paquete> en Azure Data Factory
      - funciones de módulos traducidas a C# con el módulo de compatibilidad Vb6
        (conserva la semántica de VB6, por ejemplo DateDiff o el Integer de 16 bits)
      - lo que no se puede traducir de forma mecánica (COM, lógica de UI) queda como
        "pendiente de migrar": el endpoint responde 501 y el código VB6 va en comentarios
  * <salida>/MAPEO_VB6_NET.md y mapeo.json: trazabilidad procedimiento por procedimiento

Uso:
    python vb62net.py <proyecto.vbp> --salida <carpeta> [--factoria <id-sistema>]

El resultado es un punto de partida verificable, no el sistema final: la lógica pendiente
se completa a mano (o con un agente) y se valida con pruebas de paridad.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

TIPOS = {"integer": "short", "long": "int", "currency": "decimal", "double": "double", "single": "float",
         "string": "string", "date": "DateTime", "boolean": "bool", "byte": "byte", "variant": "object", "object": "object"}
EVENTOS = {"Click", "DblClick", "Change", "Load", "Unload", "Activate", "KeyPress", "LostFocus", "GotFocus", "Timer"}
CONTROL = re.compile(r"\b((?:txt|cbo|chk|lst|opt|lbl|msk|dtp)\w+)\.(?:Text|Value)\b")


# ---------------------------------------------------------------------------
# Lectura de VB6
# ---------------------------------------------------------------------------

@dataclass
class Procedimiento:
    modulo: str
    nombre: str
    tipo: str                      # Sub | Function
    parametros: str
    retorno: str
    cuerpo: str
    comentario: str = ""
    # análisis
    clase: str = ""                # evento | funcion | infraestructura
    sql: list[dict] = field(default_factory=list)
    sps: list[dict] = field(default_factory=list)
    com: list[dict] = field(default_factory=list)
    adf: dict | None = None
    controles: list[str] = field(default_factory=list)
    catalogo: dict[str, list[str]] = field(default_factory=dict)
    destino: str = ""              # ruta del endpoint o método generado
    estado: str = ""               # Automático | Parcial | Pendiente | Reemplazado | Fuera de alcance
    notas: list[str] = field(default_factory=list)
    # evidencia del grafo de vb6graph (si se pasó --grafo)
    nodo_grafo: str = ""
    evidencia: str = ""


def leer(ruta: Path) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return ruta.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return ruta.read_text(encoding="latin-1", errors="replace")


def unir_continuaciones(texto: str) -> list[str]:
    lineas, actual = [], ""
    for linea in texto.splitlines():
        if linea.rstrip().endswith(" _"):
            actual += linea.rstrip()[:-2] + " "
        else:
            lineas.append(actual + linea)
            actual = ""
    return lineas


def leer_modulo(ruta: Path) -> tuple[str, dict[str, str], list[Procedimiento]]:
    texto = leer(ruta)
    nombre = re.search(r'Attribute VB_Name = "(\w+)"', texto)
    nombre = nombre.group(1) if nombre else ruta.stem
    constantes = dict(re.findall(r'(?im)^\s*(?:Public\s+|Private\s+|Global\s+)?Const\s+(\w+)\s+As\s+String\s*=\s*"((?:[^"]|"")*)"', texto))
    procs, actual, comentario = [], None, []
    inicio = re.compile(r"(?i)^\s*(?:Public\s+|Private\s+|Friend\s+)?(?:Static\s+)?(Sub|Function)\s+(\w+)\s*\((.*?)\)(?:\s+As\s+(\w+))?")
    for linea in unir_continuaciones(texto):
        if actual is None:
            m = inicio.match(linea)
            if m:
                actual = Procedimiento(nombre, m.group(2), m.group(1).capitalize(), m.group(3), m.group(4) or "",
                                       "", " ".join(comentario))
            elif linea.strip().startswith("'"):
                comentario.append(linea.strip()[1:].strip())
            else:
                comentario = []
        elif re.match(r"(?i)^\s*End\s+(Sub|Function)\b", linea):
            procs.append(actual)
            actual, comentario = None, []
        else:
            actual.cuerpo += linea + "\n"
    return nombre, constantes, procs


# ---------------------------------------------------------------------------
# Expresiones VB6
# ---------------------------------------------------------------------------

TOKEN = re.compile(r'\s*(?:(?P<str>"(?:[^"]|"")*")|(?P<num>\d+(?:\.\d+)?)|(?P<id>[A-Za-z_][\w]*(?:[.!][A-Za-z_]\w*)*)|(?P<op><>|<=|>=|[&+\-*/=<>(),]))')


def tokens(expr: str) -> list[tuple[str, str]]:
    salida, pos = [], 0
    while pos < len(expr):
        m = TOKEN.match(expr, pos)
        if not m or m.end() == pos:
            if expr[pos:].strip():
                raise ValueError(f"No se reconoce: {expr[pos:]}")
            break
        tipo = m.lastgroup
        salida.append((tipo, m.group(tipo)))
        pos = m.end()
    return salida


def partes_concatenadas(expr: str) -> list[tuple[str, str]]:
    """Divide una expresión por los & de primer nivel: [('lit', texto) | ('expr', código VB)]."""
    partes, actual, nivel = [], [], 0
    for tipo, valor in tokens(expr):
        if valor == "(":
            nivel += 1
        elif valor == ")":
            nivel -= 1
        if valor == "&" and nivel == 0:
            partes.append(actual)
            actual = []
        else:
            actual.append((tipo, valor))
    partes.append(actual)
    resultado = []
    for p in partes:
        if len(p) == 1 and p[0][0] == "str":
            resultado.append(("lit", p[0][1][1:-1].replace('""', '"')))
        else:
            resultado.append(("expr", "".join(v if t != "id" else f" {v} " for t, v in p).strip()))
    return resultado


def nombre_parametro(expr: str) -> str:
    m = CONTROL.search(expr)
    base = m.group(1)[3:] if m else re.sub(r"\W", "", expr.split(".")[0]).capitalize()
    return base[:1].upper() + base[1:]


def sql_parametrizado(expr: str, constantes: dict[str, str]) -> tuple[str, list[dict]] | None:
    try:
        partes = partes_concatenadas(expr)
    except ValueError:
        return None
    texto, params = "", []
    for i, (tipo, valor) in enumerate(partes):
        if tipo == "lit":
            texto += valor
        elif valor in constantes:
            texto += constantes[valor]
        else:
            nombre = nombre_parametro(valor)
            # '...' & x & '...' → @x sin las comillas
            if texto.endswith("'") and i + 1 < len(partes) and partes[i + 1][0] == "lit" and partes[i + 1][1].startswith("'"):
                texto = texto[:-1]
                partes[i + 1] = ("lit", partes[i + 1][1][1:])
            if nombre not in [p["nombre"] for p in params]:
                params.append({"nombre": nombre, "origen": valor.strip()})
            texto += f"@{nombre}"
    if not re.match(r"(?i)\s*(SELECT|INSERT|UPDATE|DELETE|EXEC|MERGE)\b", texto):
        return None
    return re.sub(r"\s+", " ", texto).strip(), params


FUNCIONES_VB = {"DateDiff": "Vb6.DateDiff", "DateAdd": "Vb6.DateAdd", "Format": "Vb6.Format", "CInt": "Vb6.CInt",
                "CLng": "Vb6.CLng", "CCur": "Vb6.CCur", "CDbl": "Vb6.CDbl", "CStr": "Vb6.CStr", "CDate": "Vb6.CDate",
                "Trim": "Vb6.Trim", "UCase": "Vb6.UCase", "LCase": "Vb6.LCase", "Len": "Vb6.Len", "Left": "Vb6.Left",
                "Right": "Vb6.Right", "Mid": "Vb6.Mid", "Round": "Vb6.Round", "Val": "Vb6.Val", "IsNull": "Vb6.IsNull"}
CONSTANTES_VB = {"Date": "Vb6.Date", "Now": "Vb6.Now", "True": "true", "False": "false", "vbCrLf": "\"\\r\\n\""}
OPERADORES = {"&": "+", "=": "==", "<>": "!=", "And": "&&", "Or": "||", "Not": "!", "Mod": "%"}


def a_csharp(expr: str, locales: set[str]) -> str | None:
    """Traduce una expresión VB6 simple a C#. Devuelve None si encuentra algo que no sabe traducir."""
    try:
        salida = []
        for tipo, valor in tokens(expr):
            if tipo == "str":
                salida.append('"' + valor[1:-1].replace('""', '\\"') + '"')
            elif tipo == "num":
                salida.append(valor + ("m" if "." in valor else ""))
            elif tipo == "op":
                salida.append(OPERADORES.get(valor, valor))
            elif valor in OPERADORES:
                salida.append(OPERADORES[valor])
            elif valor in FUNCIONES_VB:
                salida.append(FUNCIONES_VB[valor])
            elif valor in CONSTANTES_VB:
                salida.append(CONSTANTES_VB[valor])
            elif valor in locales:
                salida.append(valor)
            else:
                return None
        return re.sub(r"(\w) \(", r"\1(", " ".join(salida)).replace("( ", "(").replace(" )", ")").replace(" ,", ",")
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Análisis de procedimientos
# ---------------------------------------------------------------------------

def analizar(proc: Procedimiento, constantes: dict[str, str], es_formulario: bool) -> None:
    cuerpo = proc.cuerpo
    evento = re.fullmatch(r"(\w+?)_(\w+)", proc.nombre)
    proc.clase = "evento" if es_formulario and evento and evento.group(2) in EVENTOS else "funcion"
    proc.controles = sorted(set(CONTROL.findall(cuerpo)))

    # SQL: rs.Open "<expr>", cn  |  cn.Execute "<expr>"  |  variable = "<expr>" que parece SQL
    for m in re.finditer(r"(?im)\b(?:\w+\.(?:Open|Execute)|\w+\s*=)\s+(.+?)(?:,\s*\w+\s*)*$", cuerpo):
        r = sql_parametrizado(m.group(1).split(", cn")[0], constantes)
        if r and r[0] not in [s["sql"] for s in proc.sql]:
            proc.sql.append({"sql": r[0], "parametros": r[1], "original": m.group(0).strip()})

    # ADO Command con procedimiento almacenado
    if re.search(r"(?i)CommandType\s*=\s*adCmdStoredProc", cuerpo):
        sp = re.search(r'(?i)CommandText\s*=\s*"([^"]+)"', cuerpo)
        params = [{"nombre": n.lstrip("@"), "origen": v.strip()} for n, v in
                  re.findall(r'(?i)CreateParameter\(\s*"([^"]+)"\s*,[^,]*,[^,]*,[^,]*,\s*([^)]+)\)', cuerpo)]
        if sp:
            proc.sps.append({"nombre": sp.group(1), "parametros": params})

    # COM
    for var, progid in re.findall(r'(?i)Set\s+(\w+)\s*=\s*CreateObject\(\s*"([^"]+)"\s*\)', cuerpo):
        metodos = sorted(set(re.findall(rf"\b{var}\.(\w+)", cuerpo)))
        proc.com.append({"progid": progid, "metodos": metodos})

    # Shell dtexec → pipeline de ADF
    if re.search(r"(?i)\bShell\b", cuerpo):
        resuelto = cuerpo
        for nombre, valor in constantes.items():
            resuelto = re.sub(rf"\b{nombre}\b", valor.replace("\\", "\\\\"), resuelto)
        paquete = re.search(r"([\w-]+)\.dtsx", resuelto, re.IGNORECASE)
        if "dtexec" in resuelto.lower() and paquete:
            variables = re.findall(r"Variables\[User::(\w+)\]\.Value;\"?\s*&?\s*([^\n]+)", resuelto)
            proc.adf = {"paquete": paquete.group(1) + ".dtsx", "pipeline": "PL_" + re.sub(r"\W", "_", paquete.group(1)),
                        "parametros": {v: expr.strip() for v, expr in variables}}
        else:
            proc.notas.append("Shell a un proceso externo que no es dtexec: revisar")

    # Form_Load con combos: catálogo
    for control, valor in re.findall(r'(?i)(\w+)\.AddItem\s+"([^"]+)"', cuerpo):
        proc.catalogo.setdefault(control, []).append(valor)

    if re.search(r"(?i)\bDateDiff\s*\(", cuerpo):
        proc.notas.append("DateDiff de VB6 cuenta cambios de período, no tiempo transcurrido; Vb6.DateDiff conserva ese comportamiento")
    if any(re.search(r"(?i)WHERE.+=\s*\"\s*&", s["original"]) for s in proc.sql):
        proc.notas.append("El SQL original se armaba concatenando texto del usuario (inyección SQL); el generado está parametrizado")
    if "ADODB.Connection" in cuerpo and proc.clase == "funcion":
        proc.clase = "infraestructura"


# ---------------------------------------------------------------------------
# Generación C#
# ---------------------------------------------------------------------------

def ruta_endpoint(formulario: str, proc: Procedimiento) -> str:
    base = formulario.removeprefix("frm").lower()
    if proc.nombre.lower() == "form_load":
        return f"/api/{base}/catalogos"
    accion = re.sub(r"^(cmd|btn|mnu)", "", proc.nombre.split("_")[0], flags=re.IGNORECASE)
    return f"/api/{base}/{accion.lower()}"


def comentario_vb(proc: Procedimiento) -> str:
    origen = f"        // Origen: {proc.evidencia} · {proc.nodo_grafo} (vb6graph)\n" if proc.evidencia else ""
    return origen + "\n".join(f"        // VB6| {l.rstrip()}" for l in proc.cuerpo.strip("\n").splitlines())


def valor_parametro(origen: str, solicitud: str) -> str:
    m = CONTROL.search(origen)
    if m:
        return f"{solicitud}.{m.group(1)[3:]}"
    traducido = a_csharp(origen, set())
    return traducido or f"null /* TODO: {origen} */"


def nombre_solicitud(proc: Procedimiento) -> str:
    base = proc.nombre.replace("_", "")
    return base[:1].upper() + base[1:] + "Solicitud"


def generar_endpoint(formulario: str, proc: Procedimiento) -> str:
    ruta = ruta_endpoint(formulario, proc)
    proc.destino = ruta
    metodo = "MapGet" if (proc.catalogo or (proc.sql and not (proc.sps or proc.com or proc.adf))) else "MapPost"
    registro = f'Reemplaza VB6 {formulario}.{proc.nombre}'
    campos = sorted({c[3:] for c in proc.controles})
    solicitud_tipo = nombre_solicitud(proc)
    lineas = [f"        // {proc.comentario}" if proc.comentario else "", comentario_vb(proc)]

    if proc.catalogo:
        proc.estado = "Automático"
        valores = ", ".join(f'["{c}"] = new[] {{ {", ".join(json.dumps(v) for v in vs)} }}' for c, vs in proc.catalogo.items())
        cuerpo = f"() => Results.Ok(new Dictionary<string, string[]> {{ {valores} }})"
        return "\n".join(l for l in lineas if l) + f'\n        app.MapGet("{ruta}", {cuerpo})\n            .WithDescription("{registro}");\n'

    pendientes = []
    pasos = []
    for i, s in enumerate(proc.sql, 1):
        args = "".join(f', ("@{p["nombre"]}", (object?){valor_parametro(p["origen"], "s")})' for p in s["parametros"])
        pasos.append(f'            var consulta{i} = await db.ConsultarAsync("{s["sql"]}"{args});')
    for sp in proc.sps:
        args = "".join(f', ("@{p["nombre"]}", (object?){valor_parametro(p["origen"], "s")})' for p in sp["parametros"])
        pasos.append(f'            await db.EjecutarProcedimientoAsync("{sp["nombre"]}"{args});')
    if proc.adf:
        params = ", ".join(f'["{k}"] = {valor_parametro(v, "s")}' for k, v in proc.adf["parametros"].items())
        pasos.append(f'            var runId = await adf.IniciarAsync("{proc.adf["pipeline"]}", new Dictionary<string, string?> {{ {params} }});')
    for c in proc.com:
        pendientes.append(f"COM {c['progid']} ({', '.join(c['metodos'])}): portar la lógica del componente (ver reingenieria/rea)")
    if re.search(r"(?i)\bMsgBox\b", proc.cuerpo) and not proc.com:
        proc.notas.append("MsgBox se devuelve como respuesta JSON")

    if pendientes:
        proc.estado = "Parcial" if pasos else "Pendiente"
        pasos.append(f'            throw new PendienteDeMigrarException("{"; ".join(pendientes)}");')
    else:
        proc.estado = "Automático"
        resultado = []
        if proc.sql:
            resultado.append(f"filas = consulta{len(proc.sql)}")
        if proc.sps:
            resultado.append('ejecutado = true')
        if proc.adf:
            resultado.append(f'runId, pipeline = "{proc.adf["pipeline"]}", estado = $"/api/cargas/{{runId}}"')
        pasos.append(f"            return Results.Ok(new {{ {', '.join(resultado) or 'ok = true'} }});")

    dependencias = (["Db db"] if proc.sql or proc.sps else []) + (["AdfCliente adf"] if proc.adf else [])
    if metodo == "MapGet":
        firma = ", ".join([f"[AsParameters] {solicitud_tipo} s"] + dependencias) if campos else ", ".join(dependencias)
    else:
        firma = ", ".join([f"{solicitud_tipo} s"] + dependencias) if campos else ", ".join(dependencias)
    asincrono = "async " if any("await " in p for p in pasos) else ""
    return ("\n".join(l for l in lineas if l) + "\n" +
            f'        app.{metodo}("{ruta}", {asincrono}({firma}) =>\n        {{\n' + "\n".join(pasos) +
            f'\n        }})\n            .WithDescription("{registro}");\n')


def generar_solicitudes(procs: list[Procedimiento]) -> str:
    out = []
    for p in procs:
        campos = sorted({c[3:] for c in p.controles})
        if p.clase == "evento" and campos and not p.catalogo:
            # Los controles de VB6 entregan texto: se conservan como string y se convierten con Vb6.*
            out.append(f"public sealed record {nombre_solicitud(p)}({', '.join(f'string? {c}' for c in campos)});")
    return "\n".join(out)


def generar_funcion(proc: Procedimiento) -> str:
    params = []
    locales = set()
    for p in filter(None, (x.strip() for x in proc.parametros.split(","))):
        m = re.match(r"(?i)(?:Optional\s+)?(?:ByVal\s+|ByRef\s+)?(\w+)(?:\s+As\s+(\w+))?", p)
        params.append(f"{TIPOS.get((m.group(2) or 'variant').lower(), 'object')} {m.group(1)}")
        locales.add(m.group(1))
    retorno = TIPOS.get(proc.retorno.lower(), "object") if proc.tipo == "Function" else "void"
    asignaciones = re.findall(rf"(?im)^\s*{proc.nombre}\s*=\s*(.+)$", proc.cuerpo)
    otras = [l for l in proc.cuerpo.strip().splitlines() if l.strip() and not l.strip().startswith("'")]
    proc.destino = f"{proc.modulo}.{proc.nombre}"
    cabecera = f"    // VB6: {proc.tipo} {proc.nombre}({proc.parametros}){' As ' + proc.retorno if proc.retorno else ''}\n"
    if proc.evidencia:
        cabecera += f"    // Origen: {proc.evidencia} · {proc.nodo_grafo} (vb6graph)\n"
    if proc.tipo == "Function" and len(asignaciones) == 1 and len(otras) == 1:
        expr = a_csharp(asignaciones[0], locales)
        if expr:
            proc.estado = "Automático"
            conversion = f"checked(({retorno})({expr}))" if retorno in ("short", "int", "byte") else expr
            return cabecera + f"    public static {retorno} {proc.nombre}({', '.join(params)}) => {conversion};\n"
    proc.estado = "Pendiente"
    return (cabecera + "\n".join(f"    // VB6| {l}" for l in proc.cuerpo.strip().splitlines()) +
            f"\n    public static {retorno} {proc.nombre}({', '.join(params)}) =>\n"
            f'        throw new PendienteDeMigrarException("{proc.modulo}.{proc.nombre}: traducir a mano");\n')


PLANTILLA_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk.Web">
  <!-- Generado por tools/vb62net desde {vbp}. Regenerar en vez de editar: los cambios manuales se pierden. -->
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
    <RootNamespace>{ns}</RootNamespace>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.AspNetCore.OpenApi" Version="10.0.13" />
    <PackageReference Include="Microsoft.Data.SqlClient" Version="7.1.1" />
    <PackageReference Include="System.Security.Cryptography.Pkcs" Version="10.0.13" />
  </ItemGroup>
</Project>
"""

PLANTILLA_DOCKERFILE = """# syntax=docker/dockerfile:1
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY *.csproj ./
RUN --mount=type=secret,id=ca,required=false \\
    if [ -s /run/secrets/ca ]; then export SSL_CERT_FILE=/run/secrets/ca; fi; \\
    dotnet restore
COPY . .
RUN dotnet publish -c Release -o /app --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:10.0
WORKDIR /app
COPY --from=build /app .
USER $APP_UID
ENV ASPNETCORE_HTTP_PORTS=8080
EXPOSE 8080
ENTRYPOINT ["dotnet", "{ns}.dll"]
"""


def aplicar_grafo(carpeta: Path, modulos: list[tuple[str, bool, list[Procedimiento]]]) -> dict | None:
    """Usa el grafo de vb6graph como fuente de verdad: evidencia, código muerto y contraste de parsers."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vb6graph_puente"))
    import grafo as vb6graph  # noqa: PLC0415
    g = vb6graph.cargar(carpeta)
    if g is None:
        print(f"Aviso: no hay grafo de vb6graph en {carpeta}; se continúa sin él")
        return None
    vistos, sql_distinto, sin_resolver = set(), [], []
    for nombre_modulo, _, procs in modulos:
        for proc in procs:
            nodo = g.proc(nombre_modulo, proc.nombre)
            if nodo is None:
                continue
            vistos.add(f"{nombre_modulo}.{proc.nombre}".lower())
            proc.nodo_grafo, proc.evidencia = nodo.id, nodo.evidencia
            if len(nodo.sql) != len(proc.sql) + len(proc.sps):
                sql_distinto.append(f"{nombre_modulo}.{proc.nombre}")
            sin_resolver += [(f"{nombre_modulo}.{proc.nombre}", x) for x in nodo.sin_resolver]
            if nodo.muerto:
                proc.clase, proc.estado = "muerto", "Fuera de alcance"
                proc.destino = "— (no se migra)"
                proc.notas.append("Código muerto según vb6graph" + (" (seguro de borrar)" if nodo.seguro_borrar else ""))
    todos = {f"{m}.{p.nombre}".lower(): f"{m}.{p.nombre}" for m, _, ps in modulos for p in ps}
    return {
        "coinciden": len(vistos),
        "solo_grafo": sorted(f"{p.modulo}.{p.nombre}" for k, p in g.procs.items() if k not in todos),
        "solo_vb62net": sorted(v for k, v in todos.items() if k not in vistos),
        "sql_distinto": sql_distinto,
        "sin_resolver": sin_resolver,
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("vbp", type=Path)
    p.add_argument("--salida", type=Path, required=True)
    p.add_argument("--factoria", default="", help="nombre de la factoría ADF (id del sistema)")
    p.add_argument("--grafo", type=Path, help="carpeta con el grafo de vb6graph (grafo.db + csv/): excluye el "
                                              "código muerto, cita archivo:línea y contrasta ambos parsers")
    a = p.parse_args(argv[1:])

    vbp = leer(a.vbp)
    nombre_proyecto = (re.search(r'(?m)^Name="?([^"\r\n]+)"?', vbp) or [None, a.vbp.stem])[1]
    ns = re.sub(r"\W", "", nombre_proyecto) + ".Generado"
    archivos = [a.vbp.parent / f.split(";")[-1].strip() for f in re.findall(r"(?m)^(?:Form|Module|Class)=(.+)$", vbp)]

    constantes: dict[str, str] = {}
    modulos: list[tuple[str, bool, list[Procedimiento]]] = []
    for archivo in archivos:
        nombre, consts, procs = leer_modulo(archivo)
        constantes.update(consts)
        modulos.append((nombre, archivo.suffix.lower() == ".frm", procs))
    for _, es_form, procs in modulos:
        for proc in procs:
            analizar(proc, constantes, es_form)
    contraste = aplicar_grafo(a.grafo, modulos) if a.grafo else None

    destino = a.salida / ns
    destino.mkdir(parents=True, exist_ok=True)
    plantillas = Path(__file__).resolve().parent / "plantillas"
    for plantilla in plantillas.glob("*.cs"):
        (destino / plantilla.name).write_text(plantilla.read_text(encoding="utf-8").replace("__NS__", ns), encoding="utf-8")
    (destino / f"{ns}.csproj").write_text(PLANTILLA_CSPROJ.format(vbp=a.vbp.name, ns=ns), encoding="utf-8")
    (destino / "Dockerfile").write_text(PLANTILLA_DOCKERFILE.replace("{ns}", ns), encoding="utf-8")
    (destino / ".dockerignore").write_text("bin/\nobj/\n", encoding="utf-8")
    (destino / "appsettings.json").write_text(json.dumps({
        "Logging": {"LogLevel": {"Default": "Information", "Microsoft.AspNetCore": "Warning"}},
        "ConnectionStrings": {"Legado": ""},
        "DataFactory": {"BaseUrl": "https://management.azure.com", "SubscriptionId": "", "ResourceGroup": "",
                        "FactoryName": a.factoria, "ApiVersion": "2018-06-01"},
        "Origen": {"CadenasDeConexionVb6": sorted({re.sub(r"(?i)(password|pwd)\s*=\s*[^;]*", r"\1=****", v)
                                                   for v in constantes.values() if re.search(r"(?i)data source|provider", v)})},
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    endpoints, funciones = [], []
    todos = []
    for nombre, es_form, procs in modulos:
        for proc in procs:
            todos.append(proc)
            if proc.clase == "muerto":
                continue
            if proc.clase == "evento":
                endpoints.append((nombre, proc))
            elif proc.clase == "infraestructura":
                proc.estado, proc.destino = "Reemplazado", "Db (inyección de SqlConnection)"
                proc.notas.append("Conexión ADODB con credenciales en el código → cadena de conexión por configuración/Key Vault")
            else:
                funciones.append(generar_funcion(proc))

    codigo_endpoints = "".join(generar_endpoint(f, p) for f, p in endpoints)
    (destino / "Endpoints.cs").write_text(
        f"// Generado por tools/vb62net desde {a.vbp.name}. Las líneas \"VB6|\" son el código original.\n"
        f"namespace {ns};\n\n{generar_solicitudes([p for _, p in endpoints])}\n\n"
        "public static class EndpointsGenerados\n{\n    public static void MapEndpointsGenerados(this WebApplication app)\n    {\n"
        + codigo_endpoints + "    }\n}\n", encoding="utf-8")
    (destino / "Modulos.cs").write_text(
        f"// Funciones de módulos VB6 traducidas por tools/vb62net\nnamespace {ns};\n\n"
        "public static class Modulos\n{\n" + "\n".join(funciones) + "}\n", encoding="utf-8")

    mapeo = [{k: v for k, v in asdict(p).items() if k != "cuerpo"} for p in todos]
    (a.salida / "mapeo.json").write_text(json.dumps(mapeo, indent=2, ensure_ascii=False), encoding="utf-8")
    md = [f"# Transformación VB6 → .NET 10: {a.vbp.name}", "",
          f"Proyecto generado: `{ns}/` (`dotnet build` / `docker build`). Estado por procedimiento:", "",
          "- **Automático**: traducido y funcional.",
          "- **Parcial**: el acceso a datos está traducido; falta lógica que no es mecánica (responde 501).",
          "- **Pendiente**: requiere migración manual (responde 501 o lanza excepción).",
          "- **Reemplazado**: la infraestructura VB6 la cubre .NET (conexiones, configuración).",
          "- **Fuera de alcance**: código muerto según vb6graph; no se migra (confirmar con usuarios, checkpoint R3).", "",
          "| VB6 | Evidencia (vb6graph) | Destino .NET 10 | Estado | SQL / SP / ADF / COM | Notas |", "|---|---|---|---|---|---|"]
    for p in todos:
        detalle = []
        detalle += [f"SQL `{s['sql']}`" for s in p.sql]
        detalle += [f"SP `{s['nombre']}`" for s in p.sps]
        detalle += [f"ADF `{p.adf['pipeline']}` (desde `{p.adf['paquete']}`)"] if p.adf else []
        detalle += [f"COM `{c['progid']}`" for c in p.com]
        detalle += [f"Catálogo {', '.join(p.catalogo)}"] if p.catalogo else []
        md.append(f"| `{p.modulo}.{p.nombre}` | {('`' + p.evidencia + '`') if p.evidencia else '—'} | `{p.destino}` | {p.estado} | "
                  f"{'<br>'.join(detalle) or '—'} | {'<br>'.join(p.notas) or ''} |")
    conteo = {e: sum(1 for p in todos if p.estado == e) for e in ("Automático", "Parcial", "Pendiente", "Reemplazado", "Fuera de alcance")}
    md += ["", "**Resumen:** " + ", ".join(f"{v} {k.lower()}" for k, v in conteo.items()), "",
           "Siguiente paso: completar lo parcial/pendiente (en `sistemas/polizas/app` está el resultado terminado de este ejemplo) "
           "y validar con pruebas de paridad contra el sistema legado.", ""]
    if contraste is not None:
        md += ["## Contraste con vb6graph (dos parsers independientes)", "",
               f"vb6graph (tree-sitter) y vb62net coinciden en **{contraste['coinciden']}** procedimientos.", ""]
        md += [f"- Solo en vb6graph (vb62net no lo vio): `{x}`" for x in contraste["solo_grafo"]]
        md += [f"- Solo en vb62net (vb6graph no lo vio): `{x}`" for x in contraste["solo_vb62net"]]
        md += [f"- Distinta cantidad de SQL en `{x}`" for x in contraste["sql_distinto"]]
        md += [f"- Llamada sin resolver (enlace tardío/COM) en `{x}`: {y}" for x, y in contraste["sin_resolver"]]
        md.append("")
    (a.salida / "MAPEO_VB6_NET.md").write_text("\n".join(md), encoding="utf-8")
    print(f"{ns}: {len(endpoints)} endpoints, {len(funciones)} funciones · " + ", ".join(f"{v} {k.lower()}" for k, v in conteo.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

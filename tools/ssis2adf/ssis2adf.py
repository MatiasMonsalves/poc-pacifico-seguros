"""Convierte paquetes SSIS (.dtsx) en artefactos de Azure Data Factory.

Genera la estructura que ADF usa con integración Git (linkedService/,
dataset/, pipeline/), lista para publicar en una factoría o para cargar en el
emulador local (adf-emulador/), más un reporte por paquete con las decisiones
y los puntos que requieren revisión manual.

Uso:
    python ssis2adf.py --ssis <paquete.dtsx|carpeta> [--ssis ...] --sql <carpeta> [--sql ...]
                       --salida <carpeta_adf> [--prefijo-secretos x] [--contenedor-blob entrada]
                       [--zona-horaria "Pacific SA Standard Time"] [--key-vault-url https://...]

--sql se usa para resolver los nombres de los parámetros de los SPs: SSIS los
pasa por posición (?) y ADF los necesita por nombre.

Convierte: Execute SQL (Script o Stored Procedure), Execute Package (Execute
Pipeline), Data Flow archivo→tabla y tabla→tabla (Copy) y precedencias. Lo que
no sabe convertir queda como Wait marcador y anotado en el reporte.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "re_inventario"))
from inventario import NS_SQLTASK, analizar_dtsx, dts, version_formato_dtsx  # noqa: E402

KEY_VAULT = "LS_KeyVault"
CONDICIONES = {"Success": "Succeeded", "Failure": "Failed", "Completion": "Completed"}
# Tipos OLE DB de ParameterBinding → tipos de parámetro de SP en ADF
TIPOS_PARAM = {"3": "Int32", "20": "Int64", "11": "Boolean", "130": "String", "129": "String",
               "7": "DateTime", "133": "DateTime", "135": "DateTime", "131": "Decimal", "5": "Double"}
ORIGEN_ARCHIVO = "Microsoft.FlatFileSource"
ORIGENES_SQL = {"Microsoft.OLEDBSource", "Microsoft.SqlServer.Dts.Pipeline.DataReaderSourceAdapter"}
DESTINOS_SQL = {"Microsoft.OLEDBDestination", "Microsoft.SqlServerDestination"}
# Componentes que una Copy activity absorbe (la conversión de tipos la hace el sink)
TRANSPARENTES = {"Microsoft.DataConvert"}


@dataclass
class Opciones:
    prefijo_secretos: str = ""
    contenedor_blob: str = "entrada"
    zona_horaria: str = "Pacific SA Standard Time"
    key_vault_url: str = "https://kv-pacifico-poc.vault.azure.net/"


@dataclass
class Factoria:
    """Artefactos compartidos entre los paquetes de un mismo sistema."""
    opciones: Opciones
    params_sp: dict[str, list[str]]
    linked_services: dict[str, dict] = field(default_factory=dict)
    datasets: dict[str, dict] = field(default_factory=dict)

    def secreto(self, nombre: str) -> dict:
        prefijo = f"{self.opciones.prefijo_secretos}-" if self.opciones.prefijo_secretos else ""
        return {"type": "AzureKeyVaultSecret", "store": ref(KEY_VAULT, "LinkedServiceReference"),
                "secretName": f"{prefijo}{nombre}"}

    def key_vault(self) -> dict:
        return {"name": KEY_VAULT, "properties": {
            "type": "AzureKeyVault", "typeProperties": {"baseUrl": self.opciones.key_vault_url}}}


def nombre_adf(texto: str) -> str:
    return re.sub(r"[^\w]", "_", texto).strip("_")


def nombre_pipeline(paquete: str) -> str:
    return f"PL_{nombre_adf(Path(paquete).stem if paquete.lower().endswith('.dtsx') else paquete)}"


def ref(nombre: str, tipo: str) -> dict:
    return {"referenceName": nombre, "type": tipo}


def expr(valor: str) -> dict:
    return {"value": valor, "type": "Expression"}


def parametros_sp(carpetas: list[Path]) -> dict[str, list[str]]:
    """{'dbo.usp_x': ['Param1', ...]} leyendo CREATE PROCEDURE ... AS."""
    params = {}
    patron = re.compile(r"CREATE\s+(?:OR\s+ALTER\s+)?PROC(?:EDURE)?\s+([\w.\[\]]+)(.*?)\bAS\b",
                        re.IGNORECASE | re.DOTALL)
    for carpeta in carpetas:
        for archivo in carpeta.rglob("*.sql"):
            for m in patron.finditer(archivo.read_text(encoding="utf-8-sig", errors="replace")):
                nombre = m.group(1).replace("[", "").replace("]", "").lower()
                params[nombre if "." in nombre else f"dbo.{nombre}"] = re.findall(r"@(\w+)", m.group(2))
    return params


class Conversor:
    def __init__(self, dtsx: Path, factoria: Factoria):
        self.dtsx = dtsx
        self.raiz = ET.parse(dtsx).getroot()
        self.paquete = analizar_dtsx(dtsx, dtsx.parent)
        self.f = factoria
        self.reporte: list[tuple[str, str, str]] = []  # (elemento SSIS, resultado ADF, nota)
        self.advertencias: list[str] = []
        self.no_convertidas: list[str] = []
        self.conexiones = {c["ref_id"]: c for c in self.paquete.conexiones}
        self.archivo_por_defecto: str | None = None

    # -- Insumos ---------------------------------------------------------

    def _ejecutable(self, ref_id: str) -> ET.Element:
        for ex in self.raiz.iter(dts("Executable")):
            if ex.get(dts("refId")) == ref_id:
                return ex
        raise KeyError(ref_id)

    def _conexion_xml(self, ref_id: str) -> ET.Element:
        for cm in self.raiz.iter(dts("ConnectionManager")):
            if cm.get(dts("refId")) == ref_id:
                return cm
        raise KeyError(ref_id)

    # -- Linked services y datasets -------------------------------------

    def linked_service_sql(self, ref_id: str) -> str:
        con = self.conexiones[ref_id]
        nombre = f"LS_SQL_{nombre_adf(con['nombre'])}"
        if nombre not in self.f.linked_services:
            self.f.linked_services[nombre] = {
                "name": nombre,
                "properties": {
                    "type": "AzureSqlDatabase",
                    "annotations": [f"SSIS: {con['nombre']} ({con['tipo']})"],
                    "typeProperties": {"connectionString": self.f.secreto(f"sql-{nombre_adf(con['nombre']).lower()}-connstring")},
                },
            }
        self.reporte.append((f"Conexión {con['nombre']} ({con['tipo']})", f"Linked service {nombre} (AzureSqlDatabase)",
                             "Cadena de conexión en Key Vault; se eliminan las credenciales del paquete"))
        return nombre

    def dataset_archivo(self, ref_id: str) -> tuple[str, list[str]]:
        con = self.conexiones[ref_id]
        cm = self._conexion_xml(ref_id).find(f"{dts('ObjectData')}/{dts('ConnectionManager')}")
        columnas = [c.get(dts("ObjectName")) for c in cm.iter(dts("FlatFileColumn"))]
        delimitador = "," if not columnas else _decodificar(
            next(cm.iter(dts("FlatFileColumn"))).get(dts("ColumnDelimiter"), ","))
        self.archivo_por_defecto = re.split(r"[\\/]", con["connection_string"])[-1] or "archivo.csv"
        contenedor = self.f.opciones.contenedor_blob
        ls = "LS_Blob_Entrada"
        self.f.linked_services.setdefault(ls, {
            "name": ls,
            "properties": {
                "type": "AzureBlobStorage",
                "annotations": ["Reemplaza las carpetas compartidas de los paquetes SSIS"],
                "typeProperties": {"connectionString": self.f.secreto("blob-connstring")},
            },
        })
        ds = f"DS_{nombre_adf(con['nombre'])}"
        self.f.datasets[ds] = {
            "name": ds,
            "properties": {
                "linkedServiceName": ref(ls, "LinkedServiceReference"),
                "parameters": {"fileName": {"type": "string"}},
                "annotations": [f"SSIS: {con['nombre']} {con['connection_string']}"],
                "type": "DelimitedText",
                "typeProperties": {
                    "location": {"type": "AzureBlobStorageLocation", "container": contenedor,
                                 "fileName": expr("@dataset().fileName")},
                    "columnDelimiter": delimitador,
                    "rowDelimiter": "\r\n",
                    "encodingName": "UTF-8",
                    "firstRowAsHeader": cm.get(dts("ColumnNamesInFirstDataRow"), "False") == "True",
                    "quoteChar": "\"",
                },
                "schema": [{"name": c, "type": "String"} for c in columnas],
            },
        }
        self.reporte.append((f"Conexión {con['nombre']} ({con['tipo']}) `{con['connection_string']}`",
                             f"Linked service {ls} + dataset {ds} (DelimitedText)",
                             f"La carpeta compartida pasa a Blob Storage (contenedor `{contenedor}`); el archivo llega por parámetro"))
        if re.search(r"[*?]", con["connection_string"]):
            self.advertencias.append(f"La conexión `{con['nombre']}` usa comodines (`{con['connection_string']}`): "
                                     "en ADF use Get Metadata + ForEach o wildcardFileName")
        return ds, columnas

    def dataset_tabla(self, tabla: str, ls: str) -> str:
        limpio = tabla.replace("[", "").replace("]", "").strip()
        esquema, nombre = limpio.split(".", 1) if "." in limpio else ("dbo", limpio)
        ds = f"DS_{nombre_adf(ls.removeprefix('LS_SQL_'))}_{esquema}_{nombre}"
        self.f.datasets[ds] = {
            "name": ds,
            "properties": {
                "linkedServiceName": ref(ls, "LinkedServiceReference"),
                "type": "AzureSqlTable",
                "typeProperties": {"schema": esquema, "table": nombre},
            },
        }
        return ds

    # -- Tareas ----------------------------------------------------------

    def actividad(self, tarea) -> dict:
        ex = self._ejecutable(tarea.ref_id)
        if tarea.tipo == "Execute SQL":
            return self._execute_sql(tarea, ex)
        if tarea.tipo == "Data Flow":
            return self._data_flow(tarea)
        if tarea.tipo == "Execute Package":
            return self._execute_package(tarea, ex)
        motivo = {
            "Script Task": "contiene código C#/VB: reescribir como Azure Function, Batch o lógica en SQL",
            "Sequence Container": "las tareas internas se convirtieron al mismo nivel; revisar sus dependencias",
            "Foreach Loop": "usar ForEach (con Get Metadata para archivos)",
            "For Loop": "usar Until",
        }.get(tarea.tipo, "sin conversión automática")
        return self._marcador(tarea, motivo)

    def _marcador(self, tarea, motivo: str) -> dict:
        self.no_convertidas.append(f"{tarea.nombre} ({tarea.tipo})")
        self.advertencias.append(f"Tarea `{tarea.nombre}` ({tarea.tipo}): {motivo}. Se dejó un Wait como marcador")
        self.reporte.append((f"{tarea.tipo}: {tarea.nombre}", "Wait (marcador)", "**Revisar manualmente**"))
        return {"name": tarea.nombre, "type": "Wait", "description": f"MARCADOR {tarea.tipo}: {motivo}",
                "typeProperties": {"waitTimeInSeconds": 1}}

    def _execute_sql(self, tarea, ex: ET.Element) -> dict:
        ls = self.linked_service_sql(tarea.conexion)
        if re.search(r"GETDATE\s*\(|SYSDATETIME\s*\(", tarea.sql, re.IGNORECASE):
            self.advertencias.append(f"`{tarea.nombre}` usa GETDATE(): en Azure SQL Database devuelve hora UTC, "
                                     "no la hora local del servidor on-premise")
        m = re.fullmatch(r"\s*EXEC(?:UTE)?\s+([\w.\[\]]+)\s*(.*?)\s*;?\s*", tarea.sql, re.IGNORECASE | re.DOTALL)
        if m:
            proc = m.group(1).replace("[", "").replace("]", "")
            nombres = self.f.params_sp.get(proc.lower() if "." in proc else f"dbo.{proc.lower()}", [])
            bindings = sorted(ex.iter(f"{{{NS_SQLTASK}}}ParameterBinding"),
                              key=lambda b: int(b.get(f"{{{NS_SQLTASK}}}ParameterName", "0")))
            parametros = {}
            for i, b in enumerate(bindings):
                variable = b.get(f"{{{NS_SQLTASK}}}DtsVariableName", "")
                nombre = nombres[i] if i < len(nombres) else f"Param{i}"
                if i >= len(nombres):
                    self.advertencias.append(f"`{proc}`: no se encontró el nombre del parámetro {i}; se usó `{nombre}`")
                parametros[nombre] = {
                    "value": expr(self.valor_variable(variable)),
                    "type": TIPOS_PARAM.get(b.get(f"{{{NS_SQLTASK}}}DataType", ""), "String"),
                }
            esquema, nombre_sp = proc.split(".", 1) if "." in proc else ("dbo", proc)
            self.reporte.append((f"Execute SQL: {tarea.nombre} (`{tarea.sql}`)",
                                 f"SqlServerStoredProcedure `[{esquema}].[{nombre_sp}]`",
                                 "Parámetros posicionales (?) → por nombre: " + ", ".join(parametros) if parametros else ""))
            return {
                "name": tarea.nombre,
                "type": "SqlServerStoredProcedure",
                "linkedServiceName": ref(ls, "LinkedServiceReference"),
                "policy": {"timeout": "0.02:00:00", "retry": 0},
                "typeProperties": {"storedProcedureName": f"[{esquema}].[{nombre_sp}]",
                                   "storedProcedureParameters": parametros},
            }
        if "?" in tarea.sql:
            self.advertencias.append(f"`{tarea.nombre}` usa parámetros `?` fuera de un EXEC: revisar")
        self.reporte.append((f"Execute SQL: {tarea.nombre}", "Script (NonQuery)", ""))
        return {
            "name": tarea.nombre,
            "type": "Script",
            "linkedServiceName": ref(ls, "LinkedServiceReference"),
            "policy": {"timeout": "0.02:00:00", "retry": 0},
            "typeProperties": {"scripts": [{"type": "NonQuery", "text": tarea.sql}]},
        }

    def _execute_package(self, tarea, ex: ET.Element) -> dict:
        datos = next((e for e in ex.iter() if e.tag.endswith("ExecutePackageTask")), None)
        hijo = None
        if datos is not None:
            nodo = next((e for e in datos if e.tag.endswith("PackageName")), None)
            hijo = nodo.text.strip() if nodo is not None and nodo.text else None
            if not hijo:
                conexion = next((e for e in datos if e.tag.endswith("Connection")), None)
                if conexion is not None and conexion.text in self.conexiones:
                    hijo = re.split(r"[\\/]", self.conexiones[conexion.text]["connection_string"])[-1]
        if not hijo:
            return self._marcador(tarea, "no se pudo determinar el paquete hijo")
        pipeline = nombre_pipeline(hijo)
        enlaces = [e for e in ex.iter() if e.tag.endswith("ParameterAssignment")]
        if enlaces:
            self.advertencias.append(f"`{tarea.nombre}` pasa {len(enlaces)} parámetro(s) al paquete hijo: mapearlos en Execute Pipeline")
        self.reporte.append((f"Execute Package: {tarea.nombre} (`{hijo}`)", f"ExecutePipeline `{pipeline}`",
                             "waitOnCompletion = true, como Execute Package"))
        return {
            "name": tarea.nombre,
            "type": "ExecutePipeline",
            "typeProperties": {"pipeline": ref(pipeline, "PipelineReference"), "waitOnCompletion": True, "parameters": {}},
        }

    def _data_flow(self, tarea) -> dict:
        comps = tarea.componentes
        archivos = [c for c in comps if c["clase"] == ORIGEN_ARCHIVO]
        origenes_sql = [c for c in comps if c["clase"] in ORIGENES_SQL]
        destinos = [c for c in comps if c["clase"] in DESTINOS_SQL]
        otros = [c for c in comps if c["clase"] not in {ORIGEN_ARCHIVO, *ORIGENES_SQL, *DESTINOS_SQL, *TRANSPARENTES}]
        if len(archivos) + len(origenes_sql) != 1 or len(destinos) != 1:
            return self._marcador(tarea, f"Data Flow con {len(archivos) + len(origenes_sql)} origen(es) y {len(destinos)} "
                                         "destino(s): requiere Mapping Data Flow")

        ls_destino = self.linked_service_sql(destinos[0]["conexion"])
        tabla_destino = destinos[0].get("OpenRowset") or destinos[0].get("TableOrViewName", "")
        ds_destino = self.dataset_tabla(tabla_destino, ls_destino)
        for c in otros:
            self.advertencias.append(
                f"Data Flow `{tarea.nombre}`: el componente `{c['nombre']}` ({c['clase']}) no tiene equivalente en una "
                f"Copy activity. Opciones: Mapping Data Flow, o mover la lógica al SQL de origen o al SP que consume el destino"
                + (f" (consulta: `{c['SqlCommand']}`)" if c.get("SqlCommand") else ""))
        nota_otros = "; ver advertencias" if otros else ""
        actividad = {
            "name": tarea.nombre,
            "type": "Copy",
            "policy": {"timeout": "0.02:00:00", "retry": 0},
            "outputs": [ref(ds_destino, "DatasetReference")],
        }

        if archivos:
            ds_origen, columnas = self.dataset_archivo(archivos[0]["conexion"])
            actividad["inputs"] = [{**ref(ds_origen, "DatasetReference"),
                                    "parameters": {"fileName": expr("@pipeline().parameters.Archivo")}}]
            actividad["typeProperties"] = {
                "source": {"type": "DelimitedTextSource",
                           "storeSettings": {"type": "AzureBlobStorageReadSettings"},
                           "formatSettings": {"type": "DelimitedTextReadSettings"}},
                "sink": {"type": "AzureSqlSink", "writeBehavior": "insert"},
                "translator": {"type": "TabularTranslator",
                               "mappings": [{"source": {"name": c}, "sink": {"name": c}} for c in columnas]},
            }
            descripcion = f"Copy {ds_origen} → {ds_destino}"
        else:
            origen = origenes_sql[0]
            ls_origen = self.linked_service_sql(origen["conexion"])
            source = {"type": "AzureSqlSource"}
            if origen.get("SqlCommand"):
                source["sqlReaderQuery"] = origen["SqlCommand"]
                ds_origen = self.dataset_tabla(f"consulta_{nombre_adf(tarea.nombre)}", ls_origen)
                self.f.datasets[ds_origen]["properties"]["typeProperties"] = {}
            else:
                ds_origen = self.dataset_tabla(origen.get("OpenRowset", ""), ls_origen)
            actividad["inputs"] = [ref(ds_origen, "DatasetReference")]
            actividad["typeProperties"] = {"source": source, "sink": {"type": "AzureSqlSink", "writeBehavior": "insert"}}
            descripcion = f"Copy {ds_origen} → {ds_destino}" + (" (consulta SQL)" if origen.get("SqlCommand") else "")
            nota_otros = "Columnas mapeadas por nombre" + nota_otros

        self.reporte.append((f"Data Flow: {tarea.nombre} ({', '.join(c['nombre'] for c in comps)})", descripcion,
                             ("Data Conversion → conversión implícita a los tipos de la tabla destino; " if any(
                                 c["clase"] in TRANSPARENTES for c in comps) else "") + nota_otros))
        return actividad

    # -- Variables -------------------------------------------------------

    def valor_variable(self, variable: str) -> str:
        nombre = variable.split("::")[-1]
        var = next((v for v in self.paquete.variables if v["nombre"] == variable), None)
        if var and "GETDATE()" in var["expresion"].upper():
            return (f"@if(empty(pipeline().parameters.{nombre}), "
                    f"convertFromUtc(utcNow(), '{self.f.opciones.zona_horaria}', 'yyyy-MM-dd'), "
                    f"pipeline().parameters.{nombre})")
        return f"@pipeline().parameters.{nombre}"

    def parametros_pipeline(self) -> dict:
        params = {}
        if self.archivo_por_defecto:
            params["Archivo"] = {"type": "string", "defaultValue": self.archivo_por_defecto}
        for v in self.paquete.variables:
            nombre = v["nombre"].split("::")[-1]
            params[nombre] = {"type": "string", "defaultValue": ""}
            nota = f"Parámetro del pipeline `{nombre}`"
            if "GETDATE()" in v["expresion"].upper():
                nota += f"; si viene vacío se usa la fecha de hoy en {self.f.opciones.zona_horaria}"
                self.advertencias.append(
                    f"`{v['nombre']}` = `{v['expresion']}`: GETDATE() usa la hora local del servidor y utcNow() la hora UTC. "
                    f"Se convierte a {self.f.opciones.zona_horaria} para no cambiar de día en cargas nocturnas")
            self.reporte.append((f"Variable {v['nombre']} = `{v['expresion'] or v['valor']}`", nota, ""))
        return params

    # -- Pipeline --------------------------------------------------------

    def convertir(self) -> dict:
        version = version_formato_dtsx(self.raiz)
        if version is not None and version < 6:
            self.advertencias.append(
                f"Formato de paquete SSIS {version} (2005/2008): actualizarlo con el asistente de actualización de SSIS "
                "(Visual Studio/SSDT) a formato 2012 o superior antes de convertir; el resultado puede estar incompleto")
        por_ref = {t.ref_id: t for t in self.paquete.tareas}
        actividades = {t.ref_id: self.actividad(t) for t in self.paquete.tareas}
        parametros = self.parametros_pipeline()

        for pc in self.paquete.precedencias:
            if pc["desde"] not in por_ref or pc["hacia"] not in por_ref:
                self.advertencias.append(f"Precedencia {pc['desde']} → {pc['hacia']} hacia una tarea no encontrada: omitida")
                continue
            act = actividades[pc["hacia"]]
            act.setdefault("dependsOn", []).append({
                "activity": por_ref[pc["desde"]].nombre,
                "dependencyConditions": [CONDICIONES.get(pc["condicion"], "Succeeded")],
            })
            if pc["expresion"]:
                self.advertencias.append(f"Precedencia {por_ref[pc['desde']].nombre} → {por_ref[pc['hacia']].nombre} "
                                         f"tiene expresión `{pc['expresion']}`: usar If Condition")
            self.reporte.append((f"Precedencia {por_ref[pc['desde']].nombre} → {por_ref[pc['hacia']].nombre} ({pc['condicion']})",
                                 f"dependsOn {CONDICIONES.get(pc['condicion'])}", ""))

        # En SSIS una tarea que falla hace fallar el paquete aunque su rama de error termine bien.
        # En ADF ese patrón (try-catch) deja el pipeline en Succeeded, así que se agrega un Fail.
        lista = list(actividades.values())
        for pc in self.paquete.precedencias:
            if pc["condicion"] != "Failure" or pc["desde"] not in por_ref or pc["hacia"] not in por_ref:
                continue
            origen, manejador = por_ref[pc["desde"]].nombre, por_ref[pc["hacia"]].nombre
            lista.append({
                "name": f"Fallar tras {manejador}",
                "type": "Fail",
                "dependsOn": [{"activity": manejador, "dependencyConditions": ["Completed"]}],
                "typeProperties": {
                    "message": expr(f"@concat('{origen} falló: ', activity('{origen}').error.message)"),
                    "errorCode": "500",
                },
            })
            self.reporte.append((f"Rama de error de {origen}", f"Fail `Fallar tras {manejador}`",
                                 "Mantiene la semántica de SSIS: sin esto ADF reportaría Succeeded (patrón try-catch)"))

        return {
            "name": nombre_pipeline(self.paquete.nombre),
            "properties": {
                "description": f"Convertido desde el paquete SSIS {self.paquete.nombre} con tools/ssis2adf",
                "activities": lista,
                "parameters": parametros,
                "annotations": ["ssis2adf"],
            },
        }

    def reporte_md(self, pipeline: dict) -> str:
        lineas = [f"# Conversión SSIS → ADF: {self.paquete.nombre}", "",
                  f"Origen: `{self.dtsx.name}` · Pipeline generado: `pipeline/{pipeline['name']}.json`", "",
                  "| SSIS | ADF | Nota |", "|---|---|---|"]
        lineas += [f"| {a} | {b} | {c} |" for a, b, c in dict.fromkeys(self.reporte)]
        lineas += ["", "## Requiere revisión", ""]
        lineas += [f"- {a}" for a in dict.fromkeys(self.advertencias)] or ["- Nada"]
        return "\n".join(lineas) + "\n"


def _decodificar(valor: str) -> str:
    return re.sub(r"_x([0-9A-Fa-f]{4})_", lambda m: chr(int(m.group(1), 16)), valor)


def escribir(carpeta: Path, tipo: str, artefacto: dict) -> None:
    destino = carpeta / tipo / f"{artefacto['name']}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(artefacto, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def paquetes(rutas: list[Path]) -> list[Path]:
    encontrados = []
    for ruta in rutas:
        encontrados += sorted(ruta.rglob("*.dtsx")) if ruta.is_dir() else [ruta]
    return encontrados


def convertir(rutas_ssis: list[Path], carpetas_sql: list[Path], salida: Path, opciones: Opciones) -> dict:
    """Convierte todos los paquetes y devuelve un resumen (lo usa tools/portafolio)."""
    factoria = Factoria(opciones, parametros_sp(carpetas_sql))
    resumen = {"pipelines": [], "linked_services": 0, "datasets": 0}
    for dtsx in paquetes(rutas_ssis):
        conv = Conversor(dtsx, factoria)
        pipeline = conv.convertir()
        escribir(salida, "pipeline", pipeline)
        (salida / f"REPORTE_{pipeline['name']}.md").write_text(conv.reporte_md(pipeline), encoding="utf-8")
        resumen["pipelines"].append({
            "paquete": dtsx.name, "pipeline": pipeline["name"],
            "actividades": len(pipeline["properties"]["activities"]),
            "advertencias": list(dict.fromkeys(conv.advertencias)),
            "no_convertidas": conv.no_convertidas,
        })
    if resumen["pipelines"]:
        escribir(salida, "linkedService", factoria.key_vault())
    for ls in factoria.linked_services.values():
        escribir(salida, "linkedService", ls)
    for ds in factoria.datasets.values():
        escribir(salida, "dataset", ds)
    resumen["linked_services"] = len(factoria.linked_services) + (1 if resumen["pipelines"] else 0)
    resumen["datasets"] = len(factoria.datasets)
    resumen["secretos"] = sorted({ls["properties"]["typeProperties"]["connectionString"]["secretName"]
                                  for ls in factoria.linked_services.values()})

    lineas = ["# Conversión SSIS → ADF", "",
              "| Paquete | Pipeline | Actividades | Sin convertir | Advertencias |", "|---|---|---|---|---|"]
    lineas += [f"| `{p['paquete']}` | [{p['pipeline']}](REPORTE_{p['pipeline']}.md) | {p['actividades']} | "
               f"{len(p['no_convertidas'])} | {len(p['advertencias'])} |" for p in resumen["pipelines"]]
    lineas += ["", "## Secretos esperados en Key Vault", "", *[f"- `{s}`" for s in resumen["secretos"]], ""]
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "REPORTE_CONVERSION.md").write_text("\n".join(lineas), encoding="utf-8")
    return resumen


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ssis", action="append", type=Path, required=True)
    p.add_argument("--sql", action="append", type=Path, default=[])
    p.add_argument("--salida", type=Path, required=True)
    p.add_argument("--prefijo-secretos", default="")
    p.add_argument("--contenedor-blob", default="entrada")
    p.add_argument("--zona-horaria", default="Pacific SA Standard Time")
    p.add_argument("--key-vault-url", default="https://kv-pacifico-poc.vault.azure.net/")
    a = p.parse_args(argv[1:])
    resumen = convertir(a.ssis, a.sql, a.salida, Opciones(a.prefijo_secretos, a.contenedor_blob, a.zona_horaria, a.key_vault_url))
    for pl in resumen["pipelines"]:
        print(f"{pl['pipeline']}: {pl['actividades']} actividades, {len(pl['no_convertidas'])} sin convertir, "
              f"{len(pl['advertencias'])} advertencias")
    print(f"{resumen['linked_services']} linked services, {resumen['datasets']} datasets")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

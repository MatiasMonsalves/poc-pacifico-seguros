"""Convierte paquetes SSIS (.dtsx) en artefactos de Azure Data Factory.

Genera la estructura que ADF usa con integración Git (linkedService/,
dataset/, pipeline/), lista para publicar en una factoría o para cargar en el
emulador local (adf-emulador/), más un reporte con las decisiones y los puntos
que requieren revisión manual.

Uso:
    python ssis2adf.py <paquete.dtsx> <carpeta_sql> <carpeta_salida_adf>

<carpeta_sql> se usa para resolver los nombres de los parámetros de los SPs:
SSIS los pasa por posición (?) y ADF los necesita por nombre.

Cubre las tareas más comunes (Execute SQL, Data Flow archivo→tabla y
precedencias); lo que no sabe convertir lo deja anotado en el reporte.
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "re_inventario"))
from inventario import NS_DTS, NS_SQLTASK, analizar_dtsx, dts  # noqa: E402

KEY_VAULT = "LS_KeyVault"
CONDICIONES = {"Success": "Succeeded", "Failure": "Failed", "Completion": "Completed"}
# Tipos OLE DB de ParameterBinding → tipos de parámetro de SP en ADF
TIPOS_PARAM = {"3": "Int32", "20": "Int64", "11": "Boolean", "130": "String", "129": "String",
               "7": "DateTime", "133": "DateTime", "135": "DateTime", "131": "Decimal", "5": "Double"}
COMPONENTES_COPY = {"Microsoft.FlatFileSource", "Microsoft.DataConvert", "Microsoft.OLEDBDestination"}


def nombre_adf(texto: str) -> str:
    return re.sub(r"[^\w]", "_", texto).strip("_")


def ref(nombre: str, tipo: str) -> dict:
    return {"referenceName": nombre, "type": tipo}


def expr(valor: str) -> dict:
    return {"value": valor, "type": "Expression"}


def secreto(nombre: str) -> dict:
    return {"type": "AzureKeyVaultSecret", "store": ref(KEY_VAULT, "LinkedServiceReference"), "secretName": nombre}


class Conversor:
    def __init__(self, dtsx: Path, carpeta_sql: Path):
        self.raiz = ET.parse(dtsx).getroot()
        self.paquete = analizar_dtsx(dtsx, dtsx.parent)
        self.params_sp = self._parametros_sp(carpeta_sql)
        self.linked_services: dict[str, dict] = {}
        self.datasets: dict[str, dict] = {}
        self.reporte: list[tuple[str, str, str]] = []  # (elemento SSIS, resultado ADF, nota)
        self.advertencias: list[str] = []
        self.conexiones = {c["ref_id"]: c for c in self.paquete.conexiones}

    # -- Insumos ---------------------------------------------------------

    @staticmethod
    def _parametros_sp(carpeta: Path) -> dict[str, list[str]]:
        """{'dbo.usp_x': ['Param1', ...]} leyendo CREATE PROCEDURE ... AS."""
        params = {}
        patron = re.compile(r"CREATE\s+(?:OR\s+ALTER\s+)?PROC(?:EDURE)?\s+([\w.\[\]]+)(.*?)\bAS\b",
                            re.IGNORECASE | re.DOTALL)
        for archivo in carpeta.rglob("*.sql"):
            for m in patron.finditer(archivo.read_text(encoding="utf-8-sig")):
                nombre = m.group(1).replace("[", "").replace("]", "").lower()
                params[nombre] = re.findall(r"@(\w+)", m.group(2))
        return params

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
        if nombre not in self.linked_services:
            self.linked_services[nombre] = {
                "name": nombre,
                "properties": {
                    "type": "AzureSqlDatabase",
                    "annotations": [f"SSIS: {con['nombre']} ({con['tipo']})"],
                    "typeProperties": {"connectionString": secreto(f"sql-{nombre_adf(con['nombre']).lower()}-connstring")},
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
        ls = f"LS_Blob_{nombre_adf(con['nombre'])}"
        self.linked_services.setdefault(ls, {
            "name": ls,
            "properties": {
                "type": "AzureBlobStorage",
                "annotations": [f"SSIS: {con['nombre']} ({con['tipo']}) {con['connection_string']}"],
                "typeProperties": {"connectionString": secreto("blob-entrada-connstring")},
            },
        })
        ds = f"DS_{nombre_adf(con['nombre'])}"
        self.datasets[ds] = {
            "name": ds,
            "properties": {
                "linkedServiceName": ref(ls, "LinkedServiceReference"),
                "parameters": {"fileName": {"type": "string"}},
                "type": "DelimitedText",
                "typeProperties": {
                    "location": {"type": "AzureBlobStorageLocation", "container": "entrada",
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
                             "La carpeta compartida pasa a Blob Storage (contenedor `entrada`); el archivo llega por parámetro"))
        return ds, columnas

    def dataset_tabla(self, tabla: str, ls: str) -> str:
        esquema, nombre = (tabla.replace("[", "").replace("]", "").split(".") + ["dbo"])[:2] \
            if "." in tabla else ("dbo", tabla.strip("[]"))
        ds = f"DS_{esquema}_{nombre}"
        self.datasets[ds] = {
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
        self.advertencias.append(f"Tarea `{tarea.nombre}` ({tarea.tipo}) sin conversión automática: se dejó un Wait como marcador")
        self.reporte.append((f"{tarea.tipo}: {tarea.nombre}", "Wait (marcador)", "**Revisar manualmente**"))
        return {"name": tarea.nombre, "type": "Wait", "typeProperties": {"waitTimeInSeconds": 1}}

    def _execute_sql(self, tarea, ex: ET.Element) -> dict:
        ls = self.linked_service_sql(tarea.conexion)
        if re.search(r"GETDATE\s*\(|SYSDATETIME\s*\(", tarea.sql, re.IGNORECASE):
            self.advertencias.append(f"`{tarea.nombre}` usa GETDATE(): en Azure SQL Database devuelve hora UTC, "
                                     "no la hora local del servidor on-premise")
        m = re.fullmatch(r"\s*EXEC(?:UTE)?\s+([\w.\[\]]+)\s*(.*?)\s*;?\s*", tarea.sql, re.IGNORECASE | re.DOTALL)
        if m:
            proc = m.group(1).replace("[", "").replace("]", "")
            nombres = self.params_sp.get(proc.lower() if "." in proc else f"dbo.{proc.lower()}", [])
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
            esquema, nombre_sp = proc.split(".") if "." in proc else ("dbo", proc)
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

    def _data_flow(self, tarea) -> dict:
        origenes = [c for c in tarea.componentes if c["clase"] == "Microsoft.FlatFileSource"]
        destinos = [c for c in tarea.componentes if c["clase"] == "Microsoft.OLEDBDestination"]
        otros = [c for c in tarea.componentes if c["clase"] not in COMPONENTES_COPY]
        if len(origenes) != 1 or len(destinos) != 1:
            self.advertencias.append(f"Data Flow `{tarea.nombre}` no es archivo→tabla: requiere Mapping Data Flow manual")
            self.reporte.append((f"Data Flow: {tarea.nombre}", "—", "**Revisar manualmente**"))
            return {"name": tarea.nombre, "type": "Wait", "typeProperties": {"waitTimeInSeconds": 1}}

        ds_origen, columnas = self.dataset_archivo(origenes[0]["conexion"])
        ls_sql = self.linked_service_sql(destinos[0]["conexion"])
        ds_destino = self.dataset_tabla(destinos[0].get("OpenRowset", ""), ls_sql)
        for c in otros:
            self.advertencias.append(
                f"Data Flow `{tarea.nombre}`: el componente `{c['nombre']}` ({c['clase']}) no tiene equivalente en una "
                f"Copy activity. Opciones: Mapping Data Flow, o mover la lógica al SP que consume el staging"
                + (f" (consulta: `{c['SqlCommand']}`)" if c.get("SqlCommand") else ""))
        self.reporte.append((
            f"Data Flow: {tarea.nombre} ({', '.join(c['nombre'] for c in tarea.componentes)})",
            f"Copy {ds_origen} → {ds_destino}",
            "Data Conversion → conversión implícita a los tipos de la tabla destino"
            + ("; ver advertencias" if otros else "")))
        return {
            "name": tarea.nombre,
            "type": "Copy",
            "policy": {"timeout": "0.02:00:00", "retry": 0},
            "inputs": [{**ref(ds_origen, "DatasetReference"),
                        "parameters": {"fileName": expr("@pipeline().parameters.Archivo")}}],
            "outputs": [ref(ds_destino, "DatasetReference")],
            "typeProperties": {
                "source": {"type": "DelimitedTextSource",
                           "storeSettings": {"type": "AzureBlobStorageReadSettings"},
                           "formatSettings": {"type": "DelimitedTextReadSettings"}},
                "sink": {"type": "AzureSqlSink", "writeBehavior": "insert"},
                "translator": {"type": "TabularTranslator",
                               "mappings": [{"source": {"name": c}, "sink": {"name": c}} for c in columnas]},
            },
        }

    # -- Variables -------------------------------------------------------

    def valor_variable(self, variable: str) -> str:
        nombre = variable.split("::")[-1]
        var = next((v for v in self.paquete.variables if v["nombre"] == variable), None)
        if var and "GETDATE()" in var["expresion"].upper():
            return (f"@if(empty(pipeline().parameters.{nombre}), "
                    f"convertFromUtc(utcNow(), 'Pacific SA Standard Time', 'yyyy-MM-dd'), "
                    f"pipeline().parameters.{nombre})")
        return f"@pipeline().parameters.{nombre}"

    def parametros_pipeline(self) -> dict:
        params = {"Archivo": {"type": "string", "defaultValue": "polizas.csv"}}
        for v in self.paquete.variables:
            nombre = v["nombre"].split("::")[-1]
            params[nombre] = {"type": "string", "defaultValue": ""}
            nota = f"Parámetro del pipeline `{nombre}`"
            if "GETDATE()" in v["expresion"].upper():
                nota += "; si viene vacío se usa la fecha de hoy en hora de Chile"
                self.advertencias.append(
                    f"`{v['nombre']}` = `{v['expresion']}`: GETDATE() usa la hora local del servidor y utcNow() la hora UTC. "
                    "Se convierte a hora de Chile (Pacific SA Standard Time) para no cambiar de día en cargas nocturnas")
            self.reporte.append((f"Variable {v['nombre']} = `{v['expresion'] or v['valor']}`", nota, ""))
        return params

    # -- Pipeline --------------------------------------------------------

    def convertir(self) -> dict:
        parametros = self.parametros_pipeline()
        por_ref = {t.ref_id: t for t in self.paquete.tareas}
        actividades = {t.ref_id: self.actividad(t) for t in self.paquete.tareas}

        for pc in self.paquete.precedencias:
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
            if pc["condicion"] != "Failure":
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

        nombre = f"PL_{nombre_adf(self.paquete.nombre)}"
        return {
            "name": nombre,
            "properties": {
                "description": f"Convertido desde el paquete SSIS {self.paquete.nombre} con tools/ssis2adf",
                "activities": lista,
                "parameters": parametros,
                "annotations": ["ssis2adf"],
            },
        }

    def key_vault(self) -> dict:
        return {"name": KEY_VAULT, "properties": {
            "type": "AzureKeyVault", "typeProperties": {"baseUrl": "https://kv-pacifico-poc.vault.azure.net/"}}}


def _decodificar(valor: str) -> str:
    return re.sub(r"_x([0-9A-Fa-f]{4})_", lambda m: chr(int(m.group(1), 16)), valor)


def escribir(carpeta: Path, tipo: str, artefacto: dict) -> None:
    destino = carpeta / tipo / f"{artefacto['name']}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(artefacto, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    dtsx, carpeta_sql, salida = Path(argv[1]), Path(argv[2]), Path(argv[3])
    conv = Conversor(dtsx, carpeta_sql)
    pipeline = conv.convertir()

    escribir(salida, "linkedService", conv.key_vault())
    for ls in conv.linked_services.values():
        escribir(salida, "linkedService", ls)
    for ds in conv.datasets.values():
        escribir(salida, "dataset", ds)
    escribir(salida, "pipeline", pipeline)

    lineas = [f"# Conversión SSIS → ADF: {conv.paquete.nombre}", "",
              f"Origen: `{dtsx}` · Pipeline generado: `pipeline/{pipeline['name']}.json`", "",
              "| SSIS | ADF | Nota |", "|---|---|---|"]
    lineas += [f"| {a} | {b} | {c} |" for a, b, c in conv.reporte]
    lineas += ["", "## Requiere revisión", ""]
    lineas += [f"- {a}" for a in conv.advertencias] or ["- Nada"]
    lineas += ["", "## Secretos esperados en Key Vault", "",
               *sorted({f"- `{ls['properties']['typeProperties']['connectionString']['secretName']}`"
                        for ls in conv.linked_services.values()}), ""]
    (salida / f"REPORTE_{pipeline['name']}.md").write_text("\n".join(lineas), encoding="utf-8")
    print(f"{pipeline['name']}: {len(pipeline['properties']['activities'])} actividades, "
          f"{len(conv.linked_services) + 1} linked services, {len(conv.datasets)} datasets, "
          f"{len(conv.advertencias)} advertencias")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

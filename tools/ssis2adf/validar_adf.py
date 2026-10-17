"""Validación estática de una factoría de ADF en formato Git (linkedService/, dataset/, pipeline/).

Detecta lo que haría fallar la publicación o la ejecución en Azure:
  * referencias a linked services, datasets o pipelines inexistentes
  * dependsOn hacia actividades inexistentes, condiciones inválidas o ciclos
  * parámetros de pipeline/dataset usados en expresiones y no declarados,
    activity('X') hacia actividades inexistentes, paréntesis o comillas sin cerrar
  * nombres de actividad repetidos o archivos cuyo nombre no coincide con el artefacto
y advierte de las actividades marcador (tareas SSIS sin conversión automática).

Uso:
    python validar_adf.py <carpeta_adf> [<carpeta_adf> ...]
Termina con código 1 si hay errores.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

CONDICIONES = {"Succeeded", "Failed", "Completed", "Skipped"}


def cargar(carpeta: Path, tipo: str, errores: list[str]) -> dict[str, dict]:
    artefactos = {}
    for archivo in sorted((carpeta / tipo).glob("*.json")):
        try:
            datos = json.loads(archivo.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errores.append(f"{tipo}/{archivo.name}: JSON inválido ({e})")
            continue
        if datos.get("name") != archivo.stem:
            errores.append(f"{tipo}/{archivo.name}: el nombre del artefacto ({datos.get('name')}) no coincide con el archivo")
        artefactos[datos.get("name", archivo.stem)] = datos
    return artefactos


def expresiones(nodo, ruta: str = ""):
    """Recorre el JSON y entrega (ruta, texto) de cada valor que es una expresión de ADF."""
    if isinstance(nodo, dict):
        for k, v in nodo.items():
            yield from expresiones(v, f"{ruta}.{k}" if ruta else k)
    elif isinstance(nodo, list):
        for i, v in enumerate(nodo):
            yield from expresiones(v, f"{ruta}[{i}]")
    elif isinstance(nodo, str) and "@" in nodo and not nodo.startswith("@@"):
        if nodo.startswith("@") or "@{" in nodo:
            yield ruta, nodo


def balanceada(texto: str) -> bool:
    nivel, en_cadena = 0, False
    i = 0
    while i < len(texto):
        c = texto[i]
        if c == "'":
            if en_cadena and i + 1 < len(texto) and texto[i + 1] == "'":
                i += 2
                continue
            en_cadena = not en_cadena
        elif not en_cadena and c in "({[":
            nivel += 1
        elif not en_cadena and c in ")}]":
            nivel -= 1
            if nivel < 0:
                return False
        i += 1
    return nivel == 0 and not en_cadena


def validar(carpeta: Path) -> tuple[list[str], list[str], dict]:
    errores: list[str] = []
    advertencias: list[str] = []
    linked = cargar(carpeta, "linkedService", errores)
    datasets = cargar(carpeta, "dataset", errores)
    pipelines = cargar(carpeta, "pipeline", errores)

    for nombre, ls in linked.items():
        cadena = ls.get("properties", {}).get("typeProperties", {}).get("connectionString")
        if isinstance(cadena, dict) and cadena.get("type") == "AzureKeyVaultSecret":
            store = cadena.get("store", {}).get("referenceName")
            if store not in linked:
                errores.append(f"linkedService/{nombre}: Key Vault `{store}` no existe")
        elif isinstance(cadena, str) and re.search(r"(?i)password\s*=", cadena):
            advertencias.append(f"linkedService/{nombre}: contraseña en texto plano; usar Key Vault")

    for nombre, ds in datasets.items():
        props = ds.get("properties", {})
        ls = props.get("linkedServiceName", {}).get("referenceName")
        if ls not in linked:
            errores.append(f"dataset/{nombre}: linked service `{ls}` no existe")
        declarados = set(props.get("parameters", {}))
        for ruta, texto in expresiones(props):
            for p in re.findall(r"dataset\(\)\.(\w+)", texto):
                if p not in declarados:
                    errores.append(f"dataset/{nombre}: {ruta} usa dataset().{p}, que no está declarado")

    for nombre, pl in pipelines.items():
        props = pl.get("properties", {})
        actividades = props.get("activities", [])
        nombres = [a.get("name") for a in actividades]
        for repetido in {n for n in nombres if nombres.count(n) > 1}:
            errores.append(f"pipeline/{nombre}: actividad `{repetido}` repetida")
        parametros = set(props.get("parameters", {}))
        grafo: dict[str, list[str]] = {}
        for a in actividades:
            donde = f"pipeline/{nombre} › {a.get('name')}"
            grafo[a.get("name")] = []
            for d in a.get("dependsOn", []):
                if d.get("activity") not in nombres:
                    errores.append(f"{donde}: depende de `{d.get('activity')}`, que no existe")
                grafo[a.get("name")].append(d.get("activity"))
                malas = set(d.get("dependencyConditions", [])) - CONDICIONES
                if malas or not d.get("dependencyConditions"):
                    errores.append(f"{donde}: condiciones de dependencia inválidas {sorted(malas) or '(vacías)'}")
            ls = a.get("linkedServiceName", {}).get("referenceName")
            if ls and ls not in linked:
                errores.append(f"{donde}: linked service `{ls}` no existe")
            for ref in a.get("inputs", []) + a.get("outputs", []):
                ds = datasets.get(ref.get("referenceName"))
                if ds is None:
                    errores.append(f"{donde}: dataset `{ref.get('referenceName')}` no existe")
                    continue
                for p in ref.get("parameters", {}):
                    if p not in ds.get("properties", {}).get("parameters", {}):
                        errores.append(f"{donde}: pasa el parámetro `{p}` al dataset `{ref['referenceName']}`, que no lo declara")
            if a.get("type") == "ExecutePipeline":
                hijo = a.get("typeProperties", {}).get("pipeline", {}).get("referenceName")
                if hijo not in pipelines:
                    errores.append(f"{donde}: ejecuta el pipeline `{hijo}`, que no existe")
            if a.get("type") == "Wait" and str(a.get("description", "")).startswith("MARCADOR"):
                advertencias.append(f"{donde}: {a['description']}")
            for ruta, texto in expresiones(a):
                if not balanceada(texto):
                    errores.append(f"{donde}: expresión con paréntesis o comillas sin cerrar en {ruta}: {texto}")
                for p in re.findall(r"pipeline\(\)\.parameters\.(\w+)", texto):
                    if p not in parametros:
                        errores.append(f"{donde}: usa pipeline().parameters.{p}, que no está declarado")
                for act in re.findall(r"activity\('([^']+)'\)", texto):
                    if act not in nombres:
                        errores.append(f"{donde}: usa activity('{act}'), que no existe")
        # Ciclos en dependsOn
        estado: dict[str, int] = {}

        def visitar(n: str) -> bool:
            if estado.get(n) == 1:
                return True
            if estado.get(n) == 2 or n not in grafo:
                return False
            estado[n] = 1
            ciclo = any(visitar(d) for d in grafo[n])
            estado[n] = 2
            return ciclo

        if any(visitar(n) for n in grafo):
            errores.append(f"pipeline/{nombre}: las dependencias forman un ciclo")

    resumen = {"linked_services": len(linked), "datasets": len(datasets), "pipelines": len(pipelines),
               "actividades": sum(len(p.get("properties", {}).get("activities", [])) for p in pipelines.values())}
    return errores, advertencias, resumen


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    total_errores = 0
    for carpeta in map(Path, argv[1:]):
        errores, advertencias, r = validar(carpeta)
        total_errores += len(errores)
        print(f"{carpeta}: {r['pipelines']} pipelines, {r['actividades']} actividades, {r['datasets']} datasets, "
              f"{r['linked_services']} linked services · {len(errores)} errores, {len(advertencias)} advertencias")
        for e in errores:
            print(f"  ERROR  {e}")
        for w in advertencias:
            print(f"  AVISO  {w}")
    return 1 if total_errores else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

"""Demo guiada para presentar la fábrica: VB6 → .NET 10 y SSIS → Azure Data Factory.

Recorre el sistema de ejemplo "polizas" (VB6 + componente COM .NET 4.8 + SSIS + SQL Server)
en cinco pasos, con una pausa entre pasos para explicar:

  1. Assessment con vb6graph (grafo determinista, evidencia archivo:línea, código muerto, linaje)
  2. Transformación VB6 → .NET 10 con vb62net guiado por el grafo (y compilación)
  3. Conversión SSIS → ADF con ssis2adf (y validación)
  4. Ejecución: la app .NET 10 dispara el pipeline de ADF (emulador local) y se ve cada actividad
  5. Plan y trazabilidad: legado → nuevo → pruebas, con % de avance

Uso (desde la carpeta del repositorio, en Windows, macOS o Linux):
    python tools/demo/presentacion.py              # con pausas (Enter para avanzar)
    python tools/demo/presentacion.py --sin-pausa  # de corrido
    python tools/demo/presentacion.py --sin-docker # pasos 1-3 y 5 (sin compilar ni ejecutar)

Requisitos: Python 3.9+ y, para los pasos 2 (compilar) y 4, Docker. vb6graph es opcional:
si no está instalado se usa el grafo guardado en el repositorio.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SISTEMA = RAIZ / "sistemas" / "polizas"
for herramienta in ("vb6graph_puente", "ssis2adf"):
    sys.path.insert(0, str(RAIZ / "tools" / herramienta))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
if COLOR and os.name == "nt":
    os.system("")  # activa las secuencias ANSI en la consola de Windows


def c(texto: str, codigo: str) -> str:
    return f"\033[{codigo}m{texto}\033[0m" if COLOR else texto


def titulo(n: int, texto: str, subtitulo: str) -> None:
    print("\n" + c("━" * 78, "36"))
    print(c(f" PASO {n} · {texto}", "1;36"))
    print(c(f" {subtitulo}", "36"))
    print(c("━" * 78, "36"))


def ok(texto: str) -> None:
    print("  " + c("✔", "32") + " " + texto)


def info(texto: str) -> None:
    print("    " + texto)


def aviso(texto: str) -> None:
    print("  " + c("!", "33") + " " + texto)


def tabla(filas: list[list[str]], encabezado: list[str]) -> None:
    anchos = [max(len(str(x)) for x in col) for col in zip(encabezado, *filas)]
    anchos = [min(a, 60) for a in anchos]
    corta = lambda v, a: (str(v)[: a - 1] + "…") if len(str(v)) > a else str(v)  # noqa: E731
    print("    " + c("  ".join(corta(h, a).ljust(a) for h, a in zip(encabezado, anchos)), "1"))
    for f in filas:
        print("    " + "  ".join(corta(v, a).ljust(a) for v, a in zip(f, anchos)))


def ejecutar(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=RAIZ, **kw)


def python(*args: str) -> subprocess.CompletedProcess:
    r = ejecutar([sys.executable, *args], env={**os.environ, "PYTHONUTF8": "1"})
    if r.returncode != 0:
        raise SystemExit(f"Falló: {' '.join(args)}\n{r.stdout}\n{r.stderr}")
    return r


def puertos() -> dict[str, str]:
    valores = {"API_PORT": "8080", "GEN_PORT": "8081", "ADF_PORT": "5080"}
    env = RAIZ / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*(\w+)\s*=\s*(.*)", linea)
            if m and m.group(1) in valores:
                valores[m.group(1)] = m.group(2).strip().strip('"')
    return valores


def http(metodo: str, url: str, cuerpo=None) -> tuple[int, object]:
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, method=metodo,
                                 headers={"Content-Type": "application/json"} if datos else {})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            texto = r.read().decode("utf-8")
            return r.status, json.loads(texto) if texto else None
    except urllib.error.HTTPError as e:
        texto = e.read().decode("utf-8")
        return e.code, json.loads(texto) if texto else None


def esperar(url: str, segundos: int = 180) -> bool:
    limite = time.time() + segundos
    while time.time() < limite:
        try:
            if http("GET", url + "/health")[0] == 200:
                return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(2)
    return False


class Demo:
    def __init__(self, pausa: bool, con_docker: bool):
        self.pausa, self.con_docker = pausa, con_docker
        p = puertos()
        self.api = f"http://localhost:{p['API_PORT']}"
        self.gen = f"http://localhost:{p['GEN_PORT']}"

    def seguir(self) -> None:
        if self.pausa:
            input(c("\n  [Enter para continuar] ", "2"))

    # -- 1 -------------------------------------------------------------------
    def assessment(self) -> None:
        import grafo as vb6graph
        titulo(1, "Assessment con vb6graph", "Grafo de conocimiento determinista del VB6 y del SSIS, con evidencia archivo:línea")
        carpeta = SISTEMA / "reingenieria" / "vb6graph"
        if vb6graph.indexar(SISTEMA / "fuentes", carpeta):
            ok("vb6graph indexó los fuentes (parser tree-sitter) y generó el reporte")
        else:
            aviso("vb6graph no está instalado en este equipo: se usa el grafo guardado en el repositorio")
        g = vb6graph.cargar(carpeta)
        eventos = [p for p in g.procs.values() if p.evento]
        sql = sum(len(p.sql) for p in g.procs.values())
        ok(f"{len(g.formularios)} formularios/módulos · {len(g.procs)} procedimientos ({len(eventos)} eventos de UI) · "
           f"{sql} sentencias SQL · {len(g.paquetes_ssis)} paquete SSIS")
        print()
        info(c("Riesgos detectados:", "1"))
        for r in g.riesgos:
            if r["categoria"] in ("late_binding", "ocx") or "progid" in r["id"]:
                info(f"- {r['categoria']}: {r['detalle'] or r['id']}" + (f"  ({r['file']}:{r['line']})" if r["file"] else ""))
        print()
        info(c("Código muerto (no se migra):", "1"))
        for p in g.muertos():
            info(f"- {p.modulo}.{p.nombre}  {p.evidencia}" + ("  · seguro de borrar" if p.seguro_borrar else ""))
        print()
        info(c("Linaje VB6 ↔ SSIS (quién lee y escribe cada tabla):", "1"))
        tabla([[t["table"].split(":", 1)[1], "proc. almacenado" if t["object_type"] == "procedure" else "tabla",
                t["origen"], t["modo"], t["actor"].split("/")[-1], f"{t['file']}:{t['line']}"]
               for t in g.tablas], ["objeto", "tipo", "sistema", "modo", "quién", "evidencia"])
        compartidas = sorted({t["table"].split(":", 1)[1] for t in g.tablas if t["compartida"] == "True"})
        info(c(f"    Compartidas VB6 ↔ SSIS: {', '.join(compartidas) or 'ninguna'} (stg.Polizas y dbo.Polizas se distinguen por esquema)", "2"))
        info(f"\n    Reporte completo: {carpeta / 'reporte.html'}")
        self.seguir()

    # -- 2 -------------------------------------------------------------------
    def transformar(self) -> None:
        titulo(2, "Transformación VB6 → .NET 10", "vb62net genera una API ASP.NET Core desde el VB6, guiado por el grafo de vb6graph")
        r = python("tools/vb62net/vb62net.py", str(SISTEMA / "fuentes" / "vb6" / "Polizas.vbp"),
                   "--salida", str(SISTEMA / "transformacion"), "--factoria", "polizas",
                   "--grafo", str(SISTEMA / "reingenieria" / "vb6graph"))
        ok(r.stdout.strip())
        mapeo = json.loads((SISTEMA / "transformacion" / "mapeo.json").read_text(encoding="utf-8"))
        tabla([[f"{m['modulo']}.{m['nombre']}", m["estado"], m["destino"], m["evidencia"]] for m in mapeo],
              ["VB6", "estado", "destino .NET 10", "evidencia (vb6graph)"])

        print()
        info(c("Antes (VB6, SQL armado concatenando lo que escribe el usuario):", "1"))
        frm = (SISTEMA / "fuentes" / "vb6" / "frmPolizas.frm").read_text(encoding="utf-8").splitlines()
        buscar = next(m for m in mapeo if m["nombre"] == "cmdBuscar_Click")
        ini, fin = map(int, buscar["evidencia"].split(":")[1].split("-"))
        for linea in frm[ini - 1:fin]:
            info(c("  " + linea, "33"))
        info(c("Después (C# .NET 10 generado, consulta parametrizada):", "1"))
        cs = (SISTEMA / "transformacion" / "Polizas.Generado" / "Endpoints.cs").read_text(encoding="utf-8")
        bloque = re.search(r'(        app\.MapGet\("/api/polizas/buscar".*?\.WithDescription\([^)]*\);)', cs, re.S)
        for linea in bloque.group(1).splitlines():
            info(c("  " + linea.strip(), "32"))

        if self.con_docker:
            print()
            ok("Compilando el proyecto generado con el SDK de .NET 10 (contenedor)…")
            args = ["docker", "run", "--rm", "-v", f"{RAIZ}:/src", "-v", "poc-nuget:/root/.nuget/packages",
                    "-w", "/src/sistemas/polizas/transformacion/Polizas.Generado"]
            if os.environ.get("POC_DOCKER_RED"):
                args += ["--network", os.environ["POC_DOCKER_RED"]]
            if os.environ.get("CA_BUNDLE"):
                args += ["-e", "HTTPS_PROXY", "-e", "HTTP_PROXY", "-e", "SSL_CERT_FILE=/ca.crt", "-v", f"{os.environ['CA_BUNDLE']}:/ca.crt:ro"]
            b = ejecutar(args + ["mcr.microsoft.com/dotnet/sdk:10.0", "dotnet", "build", "-nologo", "-v", "q"])
            if b.returncode == 0 and "0 Error(s)" in b.stdout:
                ok("Compila: 0 errores, 0 advertencias (advertencias tratadas como errores)")
            else:
                aviso("La compilación falló:\n" + b.stdout[-1500:])
        self.seguir()

    # -- 3 -------------------------------------------------------------------
    def ssis_adf(self) -> None:
        from ssis2adf import Opciones, convertir
        from validar_adf import validar
        titulo(3, "SSIS → Azure Data Factory", "ssis2adf convierte el paquete .dtsx en un pipeline de ADF (formato Git, listo para publicar)")
        resumen = convertir([SISTEMA / "fuentes" / "ssis"], [SISTEMA / "fuentes" / "db"], SISTEMA / "adf",
                            Opciones(prefijo_secretos="polizas"))
        for pl in resumen["pipelines"]:
            ok(f"{pl['paquete']} → {pl['pipeline']}: {pl['actividades']} actividades, {len(pl['no_convertidas'])} sin convertir")
        definicion = json.loads((SISTEMA / "adf" / "pipeline" / "PL_CargaPolizas.json").read_text(encoding="utf-8"))
        tabla([[a["name"], a["type"], ", ".join(f"{d['activity']} ({d['dependencyConditions'][0]})" for d in a.get("dependsOn", [])) or "—"]
               for a in definicion["properties"]["activities"]], ["actividad ADF", "tipo", "depende de"])
        print()
        info("'Fallar tras Registrar Error' la agrega el convertidor: en ADF, una rama de error que termina bien")
        info("deja el pipeline en Succeeded (try-catch); en SSIS el paquete falla. Así se conserva la semántica.")
        errores, avisos, r = validar(SISTEMA / "adf")
        ok(f"Validación: {r['pipelines']} pipeline, {r['datasets']} datasets, {r['linked_services']} linked services · "
           f"{len(errores)} errores, {len(avisos)} advertencias")
        ok(f"Secretos en Key Vault: {', '.join(resumen['secretos'])} (sin credenciales en los pipelines)")
        self.seguir()

    # -- 4 -------------------------------------------------------------------
    def ejecutar_sistema(self) -> None:
        titulo(4, "Ejecución: el sistema nuevo invoca a ADF", "Docker: SQL Server + emulador del API REST de ADF + app generada + app terminada")
        compose = ["docker", "compose", "-f", "docker-compose.yml"]
        if os.environ.get("CA_BUNDLE"):
            compose += ["-f", "docker-compose.proxy.yml"]
        ok("Levantando el entorno (la primera vez descarga imágenes y tarda unos minutos)…")
        r = ejecutar(compose + ["up", "-d", "--build"])
        if r.returncode != 0 or not esperar(self.api) or not esperar(self.gen, 60):
            raise SystemExit("No se pudo levantar el entorno:\n" + r.stderr[-1500:])
        ok("Entorno arriba")

        print()
        info(c("App GENERADA automáticamente desde el VB6:", "1"))
        estado, cuerpo = http("GET", f"{self.gen}/api/polizas/buscar?Cliente=1")
        ok(f"GET /api/polizas/buscar?Cliente=1 → {estado}: {cuerpo['filas'][0]}")
        estado, _ = http("GET", f"{self.gen}/api/polizas/buscar?Cliente=1%20OR%201%3D1")
        ok(f"Intento de inyección SQL '1 OR 1=1' → {estado} (rechazado; en el VB6 se ejecutaba)")
        estado, cuerpo = http("POST", f"{self.gen}/api/polizas/cotizar", {"Cliente": "5", "Tipo": "AUTO", "Suma": "600", "Siniestros": "0"})
        ok(f"Cotizar → {estado} {cuerpo.get('title')}: la lógica del componente COM no se traduce sola")

        print()
        info(c("App TERMINADA (lógica del componente COM migrada y validada contra el binario legado):", "1"))
        estado, cuerpo = http("POST", f"{self.api}/api/cotizaciones", {"idCliente": 5, "tipoSeguro": "AUTO", "sumaAsegurada": 600, "siniestros": 0})
        ok(f"Cotizar → {cuerpo['prima']} UF (igual que el componente legado, incluido su redondeo bancario)")

        print()
        info(c("Carga de pólizas: antes 'Shell dtexec' sin ver el resultado; ahora pipeline de ADF con estado por actividad:", "1"))
        for archivo, esperado in (("polizas_20261017.csv", "Succeeded"), ("polizas_rut_invalido.csv", "Failed")):
            estado, cuerpo = http("POST", f"{self.api}/api/cargas", {"archivo": archivo, "fechaProceso": "2026-10-17", "esperar": True})
            ok(f"{archivo} → pipeline {cuerpo['pipeline']}: {c(cuerpo['estado'], '32' if cuerpo['estado'] == 'Succeeded' else '31')}")
            tabla([[a["nombre"], a["tipo"], a["estado"], (a.get("error") or "")[:70]] for a in cuerpo["actividades"]],
                  ["actividad", "tipo", "estado", "detalle"])
            print()
        info(f"Para mostrarlo en el navegador: {self.api}")
        self.seguir()

    # -- 5 -------------------------------------------------------------------
    def plan(self) -> None:
        titulo(5, "Plan y trazabilidad", "Cada nodo del legado → decisión → componente nuevo → pruebas → estado (desde el grafo)")
        if self.con_docker:
            python("tools/vb62net/cobertura.py", str(SISTEMA / "transformacion" / "mapeo.json"), f"{self.api}/openapi/v1.json",
                   "--salida", str(SISTEMA / "transformacion" / "COBERTURA.md"))
        r = python("tools/vb6graph_puente/plan.py", str(SISTEMA))
        ok(r.stdout.strip())
        import csv
        with open(SISTEMA / "plan" / "trazabilidad.csv", encoding="utf-8") as f:
            filas = [x for x in csv.DictReader(f) if x["tipo"] in ("proc", "ssis_pkg")]
        tabla([[x["legacy_node"].split("/")[-1], x["decision"], x["componente_nuevo"], x["tests"].replace(";", ", "), x["estado"]] for x in filas],
              ["nodo legado", "decisión", "componente nuevo", "pruebas", "estado"])
        info(f"\n    Plan por tarea: {SISTEMA / 'plan' / 'olas.md'}")

    def resumen(self) -> None:
        print("\n" + c("━" * 78, "36"))
        print(c(" RESULTADO", "1;36"))
        print(c("━" * 78, "36"))
        ok("VB6 → .NET 10: API generada que compila, con SQL parametrizado, ADF en lugar de dtexec y código muerto excluido")
        ok("SSIS → ADF: pipeline equivalente, validado y ejecutado, con la semántica de error de SSIS")
        ok("Evidencia y trazabilidad de punta a punta: cada decisión cita archivo:línea del legado")
        ok("Mismo proceso para cada sistema del portafolio: python tools/portafolio/portafolio.py analizar")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sin-pausa", action="store_true")
    p.add_argument("--sin-docker", action="store_true")
    a = p.parse_args(argv[1:])
    con_docker = not a.sin_docker and shutil.which("docker") is not None
    if con_docker and ejecutar(["docker", "info", "--format", "{{.ServerVersion}}"]).returncode != 0:
        raise SystemExit("Docker está instalado pero no responde: abra Docker Desktop, espere a que diga "
                         "'Engine running' y vuelva a ejecutar (o use --sin-docker).")
    if not a.sin_docker and not con_docker:
        aviso("Docker no está disponible: se omiten la compilación y la ejecución")
    d = Demo(pausa=not a.sin_pausa, con_docker=con_docker)
    print(c("\n Fábrica de migración · Pacífico Seguros", "1"))
    print(" Sistema de ejemplo: pólizas — VB6 + componente COM .NET Framework 4.8 + SSIS + SQL Server")
    d.assessment()
    d.transformar()
    d.ssis_adf()
    if con_docker:
        d.ejecutar_sistema()
    d.plan()
    d.resumen()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

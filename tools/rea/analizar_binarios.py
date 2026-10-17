"""Ingeniería inversa en lote de los binarios de un sistema (.dll, .exe, .ocx) con REA.

Para cada binario:
  * .NET (Framework o moderno): REA inspect-managed-artifact, inspect-managed-members e
    inspect-managed-native-boundaries; opcionalmente decompila con ILSpy (--decompilar).
  * VB6 (importa MSVBVM60/MSVBVM50) u otro nativo: queda marcado para análisis nativo con
    REA + Ghidra/IDA/Hopper (`rea inspect`, `rea decompile`); mientras tanto se extraen los
    textos del binario (ASCII y UTF-16, que es como VB6 guarda sus cadenas).
En todos los casos se buscan SQL, procedimientos, cadenas de conexión y ProgIds COM.

Uso:
    python analizar_binarios.py <carpeta_o_binario> [...] --salida <carpeta> [--decompilar]

Requiere `rea` en el PATH (npm install -g rea-agents). --decompilar usa Docker con la imagen
del SDK de .NET 10 (respeta CA_BUNDLE y HTTPS_PROXY si están definidos).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reconstruccion import armar_entrada  # noqa: E402

EXTENSIONES = {".dll", ".exe", ".ocx"}
RE_SQL = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|MERGE|EXEC|EXECUTE|TRUNCATE|CREATE|ALTER)\b.{6,}", re.IGNORECASE)
RE_PROC = re.compile(r"^\[?\w*\]?\.?\[?(usp|sp|pr|proc)_\w+\]?$", re.IGNORECASE)
RE_CONEXION = re.compile(r"(Data Source|Server|Initial Catalog|Provider|DSN)\s*=", re.IGNORECASE)
RE_PROGID = re.compile(r"^[A-Za-z]\w+\.[A-Za-z]\w+$")


def rea(comando: str, binario: Path) -> dict:
    r = subprocess.run(["rea", comando, str(binario), "--format", "json"], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"error": (r.stdout or r.stderr).strip()[:500]}


def textos_binario(datos: bytes, minimo: int = 6) -> list[str]:
    ascii_ = re.findall(rb"[\x20-\x7e]{%d,}" % minimo, datos)
    utf16 = re.findall(rb"(?:[\x20-\x7e]\x00){%d,}" % minimo, datos)
    return list(dict.fromkeys([t.decode("ascii") for t in ascii_] + [t.decode("utf-16-le") for t in utf16]))


def clasificar_textos(textos: list[str]) -> dict[str, list[str]]:
    ocultar = lambda t: re.sub(r"(?i)(password|pwd)\s*=\s*[^;]*", r"\1=****", t)  # noqa: E731
    return {
        "sql": [t.strip() for t in textos if RE_SQL.search(t)],
        "procedimientos": sorted({t for t in textos if RE_PROC.match(t)}),
        "conexiones": sorted({ocultar(t) for t in textos if RE_CONEXION.search(t)}),
    }


def decompilar(binario: Path, destino: Path) -> str:
    """Decompila el assembly completo a un proyecto C# con ilspycmd (en el contenedor del SDK)."""
    if not shutil.which("docker"):
        return "docker no disponible"
    destino.mkdir(parents=True, exist_ok=True)
    args = ["docker", "run", "--rm", "--network", "host", "-e", "DOTNET_ROLL_FORWARD=Major",
            "-v", f"{binario.parent.resolve()}:/entrada:ro", "-v", f"{destino.resolve()}:/salida",
            "-v", "poc-dotnet-tools:/root/.dotnet/tools"]
    if os.environ.get("CA_BUNDLE"):
        args += ["-e", "HTTPS_PROXY", "-e", "HTTP_PROXY", "-e", "SSL_CERT_FILE=/ca.crt",
                 "-v", f"{os.environ['CA_BUNDLE']}:/ca.crt:ro"]
    script = ("[ -x /root/.dotnet/tools/ilspycmd ] || dotnet tool install -g ilspycmd >/dev/null; "
              "/root/.dotnet/tools/ilspycmd --version | head -1; "
              f"/root/.dotnet/tools/ilspycmd -p -o /salida '/entrada/{binario.name}' >/dev/null")
    r = subprocess.run(args + ["mcr.microsoft.com/dotnet/sdk:10.0", "sh", "-c", script], capture_output=True, text=True)
    if r.returncode != 0:
        return "error: " + (r.stderr or r.stdout).strip()[-300:]
    return r.stdout.split(":")[-1].strip() or "desconocida"


def verificar_reconstruccion(miembros: dict, decompilado: Path, version: str, destino: Path) -> dict:
    """Importa en REA la decompilación de cada tipo, anclada al binario (token, firma e IL)."""
    resumen = {}
    for t in miembros["normalized_result"].get("types", []):
        archivo = decompilado / (t["namespace"] or "") / f"{t['name'].split('`')[0]}.cs"
        if t["full_name"].startswith("<") or ".My" in t["full_name"] or not archivo.exists():
            continue
        entrada = armar_entrada(miembros, str(archivo), t["full_name"], version)
        if not entrada["methods"]:
            continue
        ruta = destino / f"reconstruccion_{t['full_name']}.entrada.json"
        ruta.write_text(json.dumps(entrada, indent=1, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run(["rea", "import-managed-reconstruction", str(ruta), "--format", "json"], capture_output=True, text=True)
        try:
            verificado = json.loads(r.stdout)
            (destino / f"reconstruccion_{t['full_name']}.verificada.json").write_text(
                json.dumps(verificado, indent=1, ensure_ascii=False), encoding="utf-8")
            resumen[t["full_name"]] = verificado.get("normalized_result", {}).get("summary", {}).get("imported_methods", 0)
        except json.JSONDecodeError:
            resumen[t["full_name"]] = f"error: {(r.stdout or r.stderr).strip()[:200]}"
    return resumen


def analizar(binario: Path, salida: Path, con_decompilacion: bool) -> dict:
    datos = binario.read_bytes()
    base = salida / binario.name
    base.mkdir(parents=True, exist_ok=True)
    resultado: dict = {"binario": binario.name, "bytes": len(datos)}
    if datos[:2] != b"MZ":
        resultado["tipo"] = "No es un ejecutable Windows (PE)"
        return resultado

    artefacto = rea("inspect-managed-artifact", binario)
    (base / "artifact.json").write_text(json.dumps(artefacto, indent=1, ensure_ascii=False), encoding="utf-8")
    n = artefacto.get("normalized_result", {})
    if n.get("classification", {}).get("status") == "managed":
        miembros = rea("inspect-managed-members", binario)
        fronteras = rea("inspect-managed-native-boundaries", binario)
        (base / "members.json").write_text(json.dumps(miembros, indent=1, ensure_ascii=False), encoding="utf-8")
        (base / "native-boundaries.json").write_text(json.dumps(fronteras, indent=1, ensure_ascii=False), encoding="utf-8")
        m = miembros.get("normalized_result", {})
        tipos = [t["full_name"] for t in m.get("types", [])
                 if not t["full_name"].startswith(("<", "My", "ThreadSafeObjectProvider")) and ".My." not in t["full_name"]]
        literales = [l["value"] for l in m.get("user_strings", {}).get("literals", [])]
        llamadas = {f"{c['target_declaring_type'].split(',')[0]}.{c['target_name']}" for c in m.get("call_edges", [])}
        resultado.update({
            "tipo": ".NET Framework" if n["classification"].get("runtime_family") == "dotnet-framework" else ".NET",
            "assembly": f"{n.get('assembly', {}).get('name')} {n.get('assembly', {}).get('version')}",
            "framework": ", ".join(n.get("target_frameworks", [])) or "desconocido",
            "referencias": [r["name"] for r in n.get("references", [])],
            "tipos": tipos,
            "metodos": len([x for x in m.get("methods", []) if not x["name"].startswith(".")]),
            "pinvoke": fronteras.get("normalized_result", {}).get("summary", {}).get("pinvoke_import_count", 0),
            "accede_a_datos": sorted(l for l in llamadas if re.search(r"SqlClient|OleDb|Odbc|System\.Data\.", l))[:10],
            **clasificar_textos(literales),
            "siguiente_paso": "Leer la decompilación, migrar las reglas y validarlas con pruebas de paridad contra este binario",
        })
        if con_decompilacion:
            version = decompilar(binario, base / "decompilado")
            resultado["decompilacion"] = version
            if not version.startswith("error"):
                resultado["reconstruccion_verificada"] = verificar_reconstruccion(miembros, base / "decompilado", version, base)
    else:
        textos = textos_binario(datos)
        vb6 = re.search(rb"MSVBVM[56]0\.DLL", datos, re.IGNORECASE)
        resultado.update({
            "tipo": "VB6 (nativo o P-Code)" if vb6 else "Nativo (no .NET)",
            "progids_com": sorted({t for t in textos if RE_PROGID.match(t) and not t.lower().endswith((".dll", ".exe", ".ocx"))})[:30],
            **clasificar_textos(textos),
            "siguiente_paso": "Análisis nativo con REA + Ghidra/IDA/Hopper: `rea inspect` y `rea decompile`"
                              + ("; si es P-Code, un decompilador de P-Code recupera más" if vb6 else ""),
        })
        (base / "textos.txt").write_text("\n".join(textos), encoding="utf-8")
    return resultado


def reporte_md(resultados: list[dict]) -> str:
    out = ["# Binarios analizados con REA", "", "| Binario | Tipo | Framework | Tipos / métodos | SQL | Conexiones |",
           "|---|---|---|---|---|---|"]
    for r in resultados:
        out.append(f"| `{r['binario']}` | {r.get('tipo')} | {r.get('framework', '—')} | "
                   f"{len(r.get('tipos', [])) or '—'} / {r.get('metodos', '—')} | {len(r.get('sql', []))} | {len(r.get('conexiones', []))} |")
    for r in resultados:
        out += ["", f"## {r['binario']}", "", f"- Tipo: {r.get('tipo')}"]
        if r.get("assembly"):
            out.append(f"- Assembly: {r['assembly']} · {r['framework']}")
            out.append(f"- Referencias: {', '.join(r['referencias'])}")
            out.append(f"- Tipos: {', '.join(f'`{t}`' for t in r['tipos']) or '—'}")
            if r.get("pinvoke"):
                out.append(f"- P/Invoke: {r['pinvoke']} declaraciones nativas")
            if r.get("accede_a_datos"):
                out.append(f"- Acceso a datos: {', '.join(r['accede_a_datos'])}")
        if r.get("progids_com"):
            out.append(f"- ProgIds COM: {', '.join(r['progids_com'])}")
        for clave, titulo in (("sql", "SQL"), ("procedimientos", "Procedimientos"), ("conexiones", "Cadenas de conexión")):
            if r.get(clave):
                out += [f"- {titulo}:", *[f"  - `{t[:200]}`" for t in r[clave][:15]]]
        if r.get("decompilacion"):
            out.append(f"- Decompilación ILSpy {r['decompilacion']}: `{r['binario']}/decompilado/`")
        for tipo, metodos in r.get("reconstruccion_verificada", {}).items():
            out.append(f"- Reconstrucción importada en REA: `{tipo}` ({metodos} métodos anclados al binario)")
        out.append(f"- Siguiente paso: {r.get('siguiente_paso', '—')}")
    return "\n".join(out) + "\n"


def binarios(rutas: list[Path]) -> list[Path]:
    encontrados = []
    for ruta in rutas:
        if ruta.is_dir():
            encontrados += sorted(p for p in ruta.rglob("*") if p.suffix.lower() in EXTENSIONES)
        elif ruta.exists():
            encontrados.append(ruta)
    return encontrados


def analizar_todos(rutas: list[Path], salida: Path, con_decompilacion: bool = False) -> list[dict]:
    if not shutil.which("rea"):
        raise SystemExit("No se encontró `rea` en el PATH: npm install -g rea-agents")
    salida.mkdir(parents=True, exist_ok=True)
    resultados = [analizar(b, salida, con_decompilacion) for b in binarios(rutas)]
    (salida / "binarios.json").write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")
    (salida / "BINARIOS.md").write_text(reporte_md(resultados), encoding="utf-8")
    return resultados


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("rutas", nargs="+", type=Path)
    p.add_argument("--salida", type=Path, required=True)
    p.add_argument("--decompilar", action="store_true")
    a = p.parse_args(argv[1:])
    for r in analizar_todos(a.rutas, a.salida, a.decompilar):
        print(f"{r['binario']}: {r.get('tipo')} {r.get('framework', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

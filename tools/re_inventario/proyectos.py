"""Análisis de proyectos legados: VB6 (.vbp) y .NET Framework (.csproj/.vbproj).

Para cada proyecto determina el tipo de aplicación, el framework, las
referencias que complican la migración y una ruta de migración sugerida a
.NET 10. Solo lee archivos de texto; no compila ni ejecuta nada.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProyectoLegado:
    archivo: str
    plataforma: str               # VB6 | .NET Framework | .NET (SDK)
    lenguaje: str
    tipo_aplicacion: str
    framework: str = ""
    compilacion: str = ""         # VB6: código nativo o P-Code
    archivos: dict[str, int] = field(default_factory=dict)
    referencias: list[str] = field(default_factory=list)
    referencias_com: list[str] = field(default_factory=list)
    paquetes: list[str] = field(default_factory=list)
    riesgos: list[str] = field(default_factory=list)
    ruta_sugerida: str = ""
    esfuerzo: str = ""            # Bajo | Medio | Alto


# Referencias conocidas que complican la migración → explicación
RIESGOS_REFERENCIA = {
    "crystal": "Crystal Reports: no tiene versión para .NET moderno en Linux; evaluar SSRS, Power BI o una librería de PDF",
    "mscomm": "MSComm (puerto serie): dependencia de hardware/Windows",
    "winsock": "Winsock OCX: reemplazar por sockets/HTTP de .NET",
    "mapi": "MAPI: reemplazar por envío de correo por SMTP o Graph",
    "excel": "Automatización de Office (Excel): requiere Office instalado; usar una librería OpenXML",
    "word": "Automatización de Office (Word): requiere Office instalado; usar una librería OpenXML",
    "office.interop": "Office Interop: requiere Office instalado; usar una librería OpenXML",
    "dao": "DAO: acceso a datos obsoleto",
    "system.data.linq": "LINQ to SQL: no existe en .NET 10; migrar a EF Core o SqlClient",
    "entityframework": "Entity Framework 6: funciona en .NET 10, pero conviene migrar a EF Core",
    "system.runtime.remoting": ".NET Remoting: no existe en .NET 10; usar gRPC o HTTP",
    "system.web.services": "Servicios ASMX: no existen en .NET 10",
    "system.servicemodel": "WCF: en .NET 10 solo cliente; servidor con CoreWCF o reescritura REST/gRPC",
    "system.enterpriseservices": "COM+ (Enterprise Services): no existe en .NET 10",
    "microsoft.practices.enterpriselibrary": "Enterprise Library: abandonada; reemplazar sus bloques",
    "system.workflow": "Windows Workflow Foundation: no existe en .NET 10",
}

GUIDS_TIPO = {
    "349c5851-65df-11da-9384-00065b846f21": "Web",
    "e3e379df-f4c6-4180-9b81-6769533abe47": "MVC",
    "e53f8fea-eae0-44a6-8774-ffd645390401": "MVC",
    "3d9ad99f-2412-4246-b90b-4eaa41c64699": "WCF",
}

RUTAS = {
    "Web Forms": ("Reescribir en ASP.NET Core (Razor Pages o Blazor): Web Forms no existe en .NET 10", "Alto"),
    "Servicio ASMX": ("API REST en ASP.NET Core; CoreWCF si los consumidores exigen SOAP", "Medio"),
    "Servicio WCF": ("CoreWCF (mantiene el contrato SOAP) o API REST/gRPC", "Medio"),
    "ASP.NET MVC": ("ASP.NET Core MVC con .NET Upgrade Assistant", "Medio"),
    "WinForms": ("WinForms en .NET 10 (solo Windows, no contenedor Linux) o reescribir como web", "Medio"),
    "WPF": ("WPF en .NET 10 (solo Windows) o reescribir como web", "Medio"),
    "Servicio Windows": ("Worker Service .NET 10 en contenedor, o mover el proceso a ADF/Functions", "Medio"),
    "Consola": ("Aplicación de consola o Worker .NET 10 en contenedor", "Bajo"),
    "Biblioteca": ("Biblioteca .NET 10 (portar y revisar APIs con el analizador de compatibilidad)", "Bajo"),
    "VB6 aplicación con formularios": ("Reescribir: UI web o API .NET 10; reglas de negocio a una biblioteca .NET 10", "Alto"),
    "VB6 ActiveX DLL": ("Biblioteca .NET 10 sin COM; la recuperación de reglas se valida con pruebas de paridad", "Medio"),
    "VB6 ActiveX EXE": ("Servicio o API .NET 10", "Alto"),
    "VB6 control OCX": ("Componente de UI de la nueva interfaz", "Alto"),
}


def _leer(ruta: Path) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return ruta.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return ruta.read_text(encoding="latin-1", errors="replace")


def _riesgos(nombres: list[str]) -> list[str]:
    riesgos = []
    for nombre in nombres:
        bajo = nombre.lower()
        for clave, texto in RIESGOS_REFERENCIA.items():
            if clave in bajo and texto not in riesgos:
                riesgos.append(texto)
    return riesgos


def analizar_vbp(ruta: Path, base: Path) -> ProyectoLegado:
    pares = [l.split("=", 1) for l in _leer(ruta).splitlines() if "=" in l]
    valores: dict[str, list[str]] = {}
    for clave, valor in pares:
        valores.setdefault(clave.strip(), []).append(valor.strip())

    tipo = {"Exe": "VB6 aplicación con formularios", "OleDll": "VB6 ActiveX DLL",
            "OleExe": "VB6 ActiveX EXE", "Control": "VB6 control OCX"}.get(valores.get("Type", ["Exe"])[0], "VB6")
    # Reference=*\G{guid}#ver#lcid#ruta#Descripción ; Object={guid}#ver#lcid; archivo.ocx
    referencias = [r.split("#")[-1] for r in valores.get("Reference", [])]
    objetos = [o.split(";")[-1].strip() for o in valores.get("Object", [])]
    compilacion = valores.get("CompilationType", [""])[0]
    p = ProyectoLegado(
        archivo=str(ruta.relative_to(base)), plataforma="VB6", lenguaje="VB6", tipo_aplicacion=tipo,
        framework="VB6 runtime (MSVBVM60)",
        # 0 es el valor por defecto de VB6 (código nativo); -1 se interpreta como P-Code. Confirmar con el equipo del cliente.
        compilacion={"0": "Código nativo", "-1": "P-Code"}.get(compilacion, compilacion or "desconocida"),
        archivos={k.lower(): len(valores.get(k, [])) for k in ("Form", "Module", "Class", "UserControl") if valores.get(k)},
        referencias=referencias, referencias_com=objetos,
    )
    p.riesgos = _riesgos(referencias + objetos)
    if p.compilacion == "Código nativo":
        p.riesgos.append("Compilado a código nativo: si falta el fuente, del ejecutable solo se obtiene pseudocódigo (REA + Ghidra/IDA)")
    elif p.compilacion == "P-Code":
        p.riesgos.append("Compilado en P-Code: si falta el fuente, hay decompiladores específicos de P-Code que recuperan más que del nativo")
    # Llamadas a la API de Windows y objetos COM creados en tiempo de ejecución
    carpeta = ruta.parent
    codigo = "\n".join(_leer(f) for f in carpeta.iterdir() if f.suffix.lower() in (".frm", ".bas", ".cls", ".ctl"))
    declares = len(re.findall(r"(?im)^\s*(?:Private\s+|Public\s+)?Declare\s+(?:PtrSafe\s+)?(?:Function|Sub)", codigo))
    if declares:
        p.riesgos.append(f"{declares} llamada(s) Declare a DLLs de Windows")
    p.ruta_sugerida, p.esfuerzo = RUTAS.get(tipo, ("Revisar", "Alto"))
    return p


def analizar_proyecto_net(ruta: Path, base: Path) -> ProyectoLegado:
    raiz = ET.parse(ruta).getroot()
    ns = raiz.tag.split("}")[0] + "}" if raiz.tag.startswith("{") else ""

    def textos(etiqueta: str) -> list[str]:
        return [e.text.strip() for e in raiz.iter(f"{ns}{etiqueta}") if e.text and e.text.strip()]

    def incluidos(etiqueta: str) -> list[str]:
        return [e.get("Include", "") for e in raiz.iter(f"{ns}{etiqueta}") if e.get("Include")]

    sdk = bool(raiz.get("Sdk"))
    framework = (textos("TargetFrameworkVersion") or textos("TargetFramework") or textos("TargetFrameworks") or [""])[0]
    salida = (textos("OutputType") or ["Library"])[0]
    guids = {g.strip("{} ").lower() for t in textos("ProjectTypeGuids") for g in t.split(";")}
    referencias = [r.split(",")[0] for r in incluidos("Reference")]
    com = incluidos("COMReference")
    paquetes = [r for r in incluidos("PackageReference")]
    packages_config = ruta.parent / "packages.config"
    if packages_config.exists():
        paquetes += [f"{p.get('id')} {p.get('version')}" for p in ET.parse(packages_config).getroot().iter("package")]

    archivos = {}
    for patron, nombre in (("*.aspx", "aspx"), ("*.asmx", "asmx"), ("*.svc", "svc"), ("*.cshtml", "cshtml"),
                           ("*.vbhtml", "vbhtml"), ("*.xaml", "xaml")):
        n = len(list(ruta.parent.rglob(patron)))
        if n:
            archivos[nombre] = n
    codigo = " ".join(_leer(f) for f in list(ruta.parent.rglob("*.cs")) + list(ruta.parent.rglob("*.vb")))

    refs = " ".join(referencias + paquetes).lower()
    if archivos.get("aspx"):
        tipo = "Web Forms"
    elif archivos.get("asmx"):
        tipo = "Servicio ASMX"
    elif archivos.get("svc") or "WCF" in {GUIDS_TIPO.get(g) for g in guids}:
        tipo = "Servicio WCF"
    elif archivos.get("cshtml") or archivos.get("vbhtml") or "MVC" in {GUIDS_TIPO.get(g) for g in guids}:
        tipo = "ASP.NET MVC"
    elif "system.serviceprocess" in refs or "ServiceBase" in codigo:
        tipo = "Servicio Windows"
    elif "presentationframework" in refs or archivos.get("xaml"):
        tipo = "WPF"
    elif salida.lower() == "winexe" or "system.windows.forms" in refs:
        tipo = "WinForms"
    elif salida.lower() == "exe":
        tipo = "Consola"
    else:
        tipo = "Biblioteca"

    p = ProyectoLegado(
        archivo=str(ruta.relative_to(base)),
        plataforma=".NET (SDK)" if sdk and not framework.startswith(("net4", "net3", "net2")) else ".NET Framework",
        lenguaje="VB.NET" if ruta.suffix.lower() == ".vbproj" else "C#",
        tipo_aplicacion=tipo, framework=framework, archivos=archivos,
        referencias=referencias, referencias_com=com, paquetes=paquetes,
    )
    p.riesgos = _riesgos(referencias + paquetes)
    if com:
        p.riesgos.append(f"Referencias COM ({', '.join(com)}): solo Windows")
    if re.search(r"\[DllImport|Declare\s+(Function|Sub)", codigo):
        p.riesgos.append("P/Invoke a DLLs nativas: revisar disponibilidad en Linux")
    version = re.match(r"v?(\d+)\.(\d+)", framework)
    if version and int(version.group(1)) < 4:
        p.riesgos.append(f".NET Framework {framework} (CLR 2): el salto a .NET 10 es mayor; revisar APIs obsoletas")
    p.ruta_sugerida, p.esfuerzo = RUTAS.get(tipo, ("Revisar", "Medio"))
    if p.esfuerzo != "Alto" and len(p.riesgos) >= 3:
        p.esfuerzo = "Alto"
    return p


def analizar_proyecto(ruta: Path, base: Path) -> ProyectoLegado | None:
    ext = ruta.suffix.lower()
    if ext == ".vbp":
        return analizar_vbp(ruta, base)
    if ext in (".csproj", ".vbproj"):
        return analizar_proyecto_net(ruta, base)
    return None

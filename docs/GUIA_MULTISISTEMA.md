# Guía: migrar varios sistemas con la fábrica

El repositorio funciona como una **fábrica**: las herramientas (`tools/`), el emulador de ADF y el patrón de app .NET 10 son comunes, y cada sistema legado vive en su propia carpeta `sistemas/<id>/`. Los sistemas `polizas` (VB6 + COM + SSIS) y `siniestros` (.NET 3.5/4.0 + SSIS maestro/hijo) son ejemplos emulados de punta a punta.

## Estructura de un sistema

```
sistemas/<id>/
  sistema.json          id, nombre, criticidad, estado, carpetas de binarios, opciones de ADF
  fuentes/              lo que entrega el cliente (NO se versiona para sistemas reales)
    db/                 scripts T-SQL (esquema, SPs); el primero con CREATE DATABASE
    ssis/               paquetes .dtsx
    vb6/                proyectos .vbp y sus .frm/.bas/.cls
    dotnet/             proyectos .csproj/.vbproj, .config
    bin/                ejecutables y DLLs (sobre todo los que no tienen fuente)
  datos/blob/<contenedor>/   archivos de prueba (Blob Storage del emulador)
  reingenieria/         GENERADO: inventario/, rea/, RESUMEN.md, resumen.json
                        MANUAL: HALLAZGOS.md (reglas recuperadas y problemas, revisado por una persona)
  adf/                  GENERADO: pipelines, datasets y linked services de ADF + reportes de conversión
  app/                  sistema nuevo .NET 10 (cuando se construye; ver sistemas/polizas/app)
```

## Proceso por sistema

1. **Crear la carpeta**
   ```bash
   python3 tools/portafolio/portafolio.py nuevo cobranza --nombre "Cobranza"
   ```
2. **Copiar los fuentes** en `sistemas/cobranza/fuentes/` y completar `sistema.json` (criticidad, descripción y, si los binarios no están en `fuentes/bin`, la lista `binarios`).
3. **Analizar** (inventario + REA + conversión a ADF + resumen):
   ```bash
   python3 tools/portafolio/portafolio.py analizar --solo cobranza --decompilar
   ```
   Sin `--solo` analiza todos los sistemas y regenera `portafolio/PORTAFOLIO.md`.
4. **Revisar** `reingenieria/RESUMEN.md` y escribir `reingenieria/HALLAZGOS.md`: reglas recuperadas (de la decompilación de REA/ILSpy y del código fuente), inconsistencias y decisiones de negocio pendientes. Este paso es de una persona: las herramientas encuentran, no deciden.
5. **Completar ADF**: reemplazar los `Wait` con descripción `MARCADOR` (Script Tasks, Send Mail, contenedores) y resolver las advertencias del reporte de conversión.
6. **Probar en el emulador**: agregar los secretos `KeyVault__<id>-...` del reporte al servicio `adf-emulador` de `docker-compose.yml`, levantar el entorno y ejecutar los pipelines (`docker compose up -d --build`).
7. **Transformar el VB6**: `python3 tools/vb62net/vb62net.py sistemas/<id>/fuentes/vb6/<Proyecto>.vbp --salida sistemas/<id>/transformacion --factoria <id>` genera un proyecto .NET 10 que compila y `MAPEO_VB6_NET.md` (lo hace también `scripts/verificar.sh`).
8. **Completar el sistema nuevo .NET 10** partiendo de lo generado y tomando `sistemas/polizas/app` como patrón: dominio con las reglas migradas, **pruebas de paridad contra el binario legado**, API que invoca ADF con `ClienteDataFactory` (cambia solo `DataFactory__FactoryName`).
   Marcar cada endpoint con `.WithDescription("Reemplaza VB6 <formulario>.<evento>")` y definir `appUrl` en `sistema.json` para que `tools/vb62net/cobertura.py` compruebe que no falta ningún evento.
9. **Agregar verificaciones** del sistema a `scripts/demo.sh` y correr `scripts/verificar.sh`.

## Qué hace cada herramienta

| Herramienta | Entrada | Salida |
|---|---|---|
| `tools/re_inventario` | `fuentes/` | SSIS (conexiones, flujo, SQL), T-SQL (objetos, lecturas/escrituras), código (SQL embebido, conexiones, COM, `Shell`), **proyectos** (tipo, framework, riesgos, ruta de migración) y matriz de dependencias |
| `tools/rea/analizar_binarios.py` | `.dll`/`.exe`/`.ocx` | .NET: identidad, framework, tipos, acceso a datos, SQL y conexiones embebidas, decompilación ILSpy e import de la reconstrucción en REA. VB6/nativo: detección, textos (SQL, conexiones, ProgIds) y siguiente paso con Ghidra/IDA/Hopper |
| `tools/ssis2adf` | `.dtsx` + scripts SQL | Pipelines (Execute SQL → Script/SP, Execute Package → Execute Pipeline, Data Flow archivo→tabla y tabla→tabla → Copy, rama de error + Fail), datasets y linked services con secretos en Key Vault prefijados por sistema |
| `tools/portafolio` | `sistemas/*/sistema.json` | Ejecuta todo lo anterior, `RESUMEN.md` por sistema y `portafolio/PORTAFOLIO.md` con complejidad, orden sugerido, BDs compartidas y riesgos transversales |
| `adf-emulador` | `sistemas/<id>/adf` | API REST de ADF local; una factoría por sistema (`.../factories/<id>/...`) |

## Rutas de migración que sugiere el inventario

| Tecnología legada | Ruta sugerida | Esfuerzo base |
|---|---|---|
| VB6 con formularios | Reescribir UI (web o API .NET 10); reglas a una biblioteca .NET 10 con paridad | Alto |
| VB6 ActiveX DLL / componente COM .NET | Biblioteca .NET 10 sin COM, con pruebas de paridad contra el binario | Medio |
| ASP.NET Web Forms | ASP.NET Core (Razor Pages o Blazor) | Alto |
| Servicio ASMX | API REST ASP.NET Core (CoreWCF si los consumidores exigen SOAP) | Medio |
| Servicio WCF | CoreWCF o REST/gRPC | Medio |
| ASP.NET MVC 5 | ASP.NET Core MVC con .NET Upgrade Assistant | Medio |
| WinForms / WPF | .NET 10 en Windows (no contenedor Linux) o reescribir como web | Medio |
| Servicio Windows | Worker Service .NET 10 en contenedor, o el proceso a ADF/Functions | Medio |
| Biblioteca / consola | .NET 10 | Bajo |
| SSIS | ADF (pipelines convertidos); Azure-SSIS IR como plan B para paquetes difíciles | según marcadores |

El esfuerzo sube a Alto cuando un proyecto acumula tres o más riesgos (Crystal Reports, Office Interop, LINQ to SQL, Remoting, COM, P/Invoke, .NET 2.0/3.5...).

## Límites conocidos

- **SSIS 2005/2008** (`PackageFormatVersion` 2 o 3): se detectan y se avisa; hay que actualizarlos con el asistente de SSIS (Visual Studio/SSDT) antes de convertir.
- **Ejecutables VB6 sin fuente**: REA necesita Ghidra, IDA o Hopper para el pseudocódigo. Esta ruta no se probó con un ejecutable VB6 real; sin motor nativo la herramienta solo extrae textos.
- **Data Flows complejos** (varios orígenes/destinos, Lookups, transformaciones): quedan como marcador para Mapping Data Flow o para mover la lógica a SQL.
- El **puntaje de complejidad** sirve para ordenar el portafolio, no es una estimación de horas.
- El emulador cubre las actividades que generan los convertidores; la validación final se hace en una factoría real.

## Seguridad de los fuentes del cliente

`.gitignore` excluye `sistemas/*/fuentes/` y las decompilaciones de los sistemas reales (solo se versionan los dos ejemplos emulados). Los reportes generados no incluyen contraseñas (se reemplazan por `****`), pero sí SQL y nombres de servidores: revise antes de compartirlos fuera del equipo.

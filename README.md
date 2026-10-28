# Fábrica de migración Pacífico Seguros: VB6 / .NET antiguo / SSIS → .NET 10 + Azure Data Factory

Kit para hacer ingeniería inversa de **varios sistemas legados** (aplicaciones **VB6** y **.NET Framework** antiguas, ETL **SSIS**, lógica en **T-SQL**) y llevarlos a:

- **.NET 10 LTS** en contenedores Linux.
- **Azure Data Factory**: los paquetes SSIS se convierten en pipelines.
- El sistema nuevo **invoca a ADF por su API REST**. En local lo hace contra un emulador con el mismo API, para reproducir la problemática sin una suscripción de Azure.

La ingeniería inversa de los binarios sin fuente usa **[REA](https://github.com/morluto/rea)**, y las reglas recuperadas se validan con pruebas de paridad contra el binario legado.

**Presentar la demo en Windows: [docs/DEMO_WINDOWS.md](docs/DEMO_WINDOWS.md)** (`scripts\windows\presentacion.ps1`) · **Instalarlo en su equipo: [docs/INSTALACION_LOCAL.md](docs/INSTALACION_LOCAL.md)** · **Cómo verificar que funciona: [docs/COMO_VERIFICAR.md](docs/COMO_VERIFICAR.md)** (`scripts/verificar.sh`, un comando) · **Cómo usarlo con un sistema nuevo: [docs/GUIA_MULTISISTEMA.md](docs/GUIA_MULTISISTEMA.md)**

## Sistemas de ejemplo (emulados)

| Sistema | Legado | Resultado |
|---|---|---|
| [`polizas`](sistemas/polizas/reingenieria/HALLAZGOS.md) | VB6 + componente COM .NET 4.8 + SSIS (archivo → tabla) | Análisis, pipeline ADF, **transformación automática VB6 → .NET 10** (`transformacion/`) y **app .NET 10 terminada** con pantalla web y pruebas de paridad |
| [`siniestros`](sistemas/siniestros/reingenieria/HALLAZGOS.md) | ASMX .NET 3.5 + WinForms .NET 4.0 con Crystal Reports + DLL .NET 4.0 sin fuente + SSIS maestro/hijo (tabla → tabla) | Análisis, REA y pipelines ADF ejecutados en el emulador |

Consolidado: [portafolio/PORTAFOLIO.md](portafolio/PORTAFOLIO.md).

## Uso rápido

Requisitos: Python 3.9+, Docker con Compose y, para binarios, `npm install -g rea-agents` (Node.js ≥ 22.19). `scripts/requisitos.sh` revisa el equipo; en Windows basta Docker Desktop + PowerShell ([instalación](docs/INSTALACION_LOCAL.md), [demo](docs/DEMO_WINDOWS.md)).

```bash
# Crear un sistema y analizarlo (inventario + REA + SSIS→ADF + resumen)
python3 tools/portafolio/portafolio.py nuevo cobranza --nombre "Cobranza"
#   ...copiar los fuentes en sistemas/cobranza/fuentes/...
python3 tools/portafolio/portafolio.py analizar --solo cobranza --decompilar

# Analizar todo el portafolio
python3 tools/portafolio/portafolio.py analizar --decompilar

# Entorno local: SQL Server + BDs legadas + emulador ADF (una factoría por sistema) + app de pólizas
docker compose up -d --build
scripts/demo.sh            # 19 verificaciones de punta a punta (pólizas y siniestros)
# o todo de una vez (análisis, transformación, validación, pruebas, entorno, punta a punta, cobertura):
scripts/verificar.sh
# en Windows con Docker Desktop, desde PowerShell (sin Ubuntu):
#   powershell -ExecutionPolicy Bypass -File scripts\windows\verificar.ps1
```

Detrás de un proxy con certificado propio: `CA_BUNDLE=/ruta/ca.crt docker compose -f docker-compose.yml -f docker-compose.proxy.yml up -d --build`.

| Servicio | URL |
|---|---|
| App de pólizas terminada (.NET 10) | **http://localhost:8080** (pantalla web) · OpenAPI en `/openapi/v1.json` |
| App de pólizas generada por vb62net | http://localhost:8081 · OpenAPI en `/openapi/v1.json` |
| Emulador ADF | `http://localhost:5080/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.DataFactory/factories/{id-del-sistema}/...` |
| SQL Server | `localhost,1433` (usuario `sa`, clave en `.env.example`) |

## Estructura

```
sistemas/<id>/            Un sistema legado: sistema.json, fuentes/, reingenieria/, adf/, datos/, app/
portafolio/               PORTAFOLIO.md y portafolio.json (generados)
tools/
  portafolio/             Orquestador: analiza todos los sistemas y crea sistemas nuevos
  re_inventario/          Inventario: SSIS, T-SQL, código VB6/.NET y proyectos (ruta de migración)
  rea/                    REA en lote sobre binarios + import de la reconstrucción ILSpy
  ssis2adf/               Convertidor SSIS → ADF (varios paquetes, Execute Package, tabla→tabla) y validador
  vb62net/                Transformación VB6 → .NET 10 (proyecto generado + mapeo) y chequeo de cobertura
  generar-legado/         Fuentes usados solo para fabricar los binarios de los sistemas emulados
adf-emulador/             Emulador del API REST de ADF (.NET 10), pruebas en adf-emulador.Pruebas/
infra/db-init.sh          Crea las BDs de todos los sistemas en docker compose
scripts/                  demo.sh (punta a punta) y dotnet.sh (SDK .NET 10 en contenedor)
docs/                     Guía multisistema, arquitectura, mapeo SSIS → ADF y plan
```

## Pruebas

```bash
DOTNET_DIR=sistemas/polizas/app scripts/dotnet.sh test     # 30 pruebas, incluida la paridad con el binario legado
DOTNET_DIR=adf-emulador.Pruebas scripts/dotnet.sh test     # 12 pruebas del lenguaje de expresiones
DOTNET_DIR=tools/vb62net/Vb62Net.Pruebas scripts/dotnet.sh test  # 11 pruebas de la semántica VB6 en el código generado
scripts/demo.sh                                            # con docker compose levantado
```

## Documentación

- [Instalación en su equipo (Windows/WSL2, macOS, Linux)](docs/INSTALACION_LOCAL.md)
- [Cómo verificar que funciona](docs/COMO_VERIFICAR.md)
- [Guía para varios sistemas](docs/GUIA_MULTISISTEMA.md)
- [Arquitectura legado → objetivo → local, y alcance del emulador](docs/ARQUITECTURA.md)
- [Equivalencias SSIS → ADF](docs/MAPEO_SSIS_ADF.md)
- [Plan de la POC](docs/PLAN_POC.md)

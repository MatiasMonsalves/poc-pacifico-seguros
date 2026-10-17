# POC Pacífico Seguros: ingeniería inversa y migración a la nube

POC que emula el sistema legado del cliente (app **VB6** + componente **.NET Framework 4.8** por COM + ETL **SSIS** + lógica en **T-SQL**) y lo lleva a:

- **.NET 10 LTS**: API ASP.NET Core en contenedor Linux que reemplaza la app VB6 y el componente COM.
- **Azure Data Factory**: el paquete SSIS se convierte en un pipeline de ADF.
- El sistema nuevo **invoca a ADF por su API REST**. En local lo hace contra un emulador con el mismo API, para reproducir la problemática del cliente sin una suscripción de Azure.

La ingeniería inversa del componente compilado se hizo con **[REA](https://github.com/morluto/rea)** (solo desde el binario) y se validó con pruebas de paridad que ejecutan el binario legado.

## Levantar y probar

Requisitos: Docker con Compose y Python 3.

```bash
docker compose up -d --build   # sqlserver + db-init + adf-emulador + api
scripts/demo.sh                # 12 verificaciones de punta a punta
```

Detrás de un proxy con certificado propio: `CA_BUNDLE=/ruta/ca.crt docker compose -f docker-compose.yml -f docker-compose.proxy.yml up -d --build`.

| Servicio | URL |
|---|---|
| API (.NET 10) | http://localhost:8080 · OpenAPI en `/openapi/v1.json` |
| Emulador ADF | http://localhost:5080/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.DataFactory/factories/{f}/... |
| SQL Server | `localhost,1433` (usuario `sa`, clave en `.env.example`) |

### API

| Endpoint | Reemplaza en VB6 |
|---|---|
| `GET /api/clientes/{id}/polizas` | `cmdBuscar_Click` (SQL concatenado) |
| `POST /api/cotizaciones` `{idCliente, tipoSeguro, sumaAsegurada, siniestros}` | `cmdCotizar_Click` + componente COM |
| `POST /api/primas/recalcular` `{fechaProceso?}` | `cmdRecalcular_Click` |
| `POST /api/cargas` `{archivo, fechaProceso?, esperar?}` → ejecuta `PL_CargaPolizas` en ADF | `cmdCargar_Click` (`Shell dtexec`) |
| `GET /api/cargas/{runId}` → estado del pipeline y de cada actividad | (no existía) |

Archivos de prueba en `data/blob/entrada/`: `polizas_20261017.csv` (válido), `polizas_rut_invalido.csv` (falla la consolidación → rama de error) y `polizas_formato_invalido.csv` (falla la copia).

## Estructura

```
legacy/                  Sistema legado emulado (lo que entregaría el cliente)
  db/                    Esquema, SPs y datos de la BD Seguros
  ssis/                  CargaPolizas.dtsx
  vb6/                   App VB6 (Polizas.vbp, frmPolizas.frm, modConexion.bas)
  componente-net/bin/    Pacifico.Tarificador.dll: SOLO el binario
reingenieria/            Resultados de la ingeniería inversa
  HALLAZGOS.md           Reglas recuperadas y problemas detectados (P1–P9)
  rea/                   Evidencia de REA (artifact, members, decompilación, reconstrucción verificada)
  inventario/            Inventario de SSIS, T-SQL y VB6
adf/                     Pipeline, datasets y linked services de ADF (formato Git), generados desde el SSIS
app/                     Sistema nuevo .NET 10 (Dominio, Api, Pruebas con paridad contra el binario legado)
adf-emulador/            Emulador local del API REST de ADF (.NET 10) y sus pruebas en adf-emulador.Pruebas/
tools/
  re_inventario/         Inventario automático (SSIS, T-SQL, VB6/.NET)
  ssis2adf/              Convertidor SSIS → ADF
  rea/                   Arma la entrada de `rea import-managed-reconstruction` desde ILSpy
  generar-legado/        Fuente usado solo para fabricar el binario legado emulado
infra/db-init.sh         Inicialización de la BD en docker compose
scripts/                 demo.sh (prueba de punta a punta) y dotnet.sh (SDK .NET 10 en contenedor)
docs/                    Plan, arquitectura y mapeo SSIS → ADF
```

## Regenerar los artefactos

```bash
# Inventario del legado
python3 tools/re_inventario/inventario.py legacy reingenieria/inventario
# SSIS → ADF (los nombres de parámetros de los SPs se leen de legacy/db)
python3 tools/ssis2adf/ssis2adf.py legacy/ssis/CargaPolizas.dtsx legacy/db adf
# Ingeniería inversa con REA: ver reingenieria/HALLAZGOS.md § "Cómo reproducir"
# Pruebas (.NET 10 en contenedor; no requiere instalar el SDK)
DOTNET_DIR=app scripts/dotnet.sh test
DOTNET_DIR=adf-emulador.Pruebas scripts/dotnet.sh test
```

## Documentación

- [Hallazgos de la ingeniería inversa](reingenieria/HALLAZGOS.md)
- [Arquitectura legado → objetivo → local, y alcance del emulador](docs/ARQUITECTURA.md)
- [Reporte de conversión SSIS → ADF](adf/REPORTE_PL_CargaPolizas.md)
- [Equivalencias SSIS → ADF](docs/MAPEO_SSIS_ADF.md)
- [Plan de la POC](docs/PLAN_POC.md)

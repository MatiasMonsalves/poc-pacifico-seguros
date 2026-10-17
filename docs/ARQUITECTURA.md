# Arquitectura: legado → objetivo → entorno local

## Sistema legado de ejemplo: pólizas (emulado en `sistemas/polizas/fuentes/`)

```mermaid
flowchart LR
    U[Usuario] --> VB6["App VB6<br/>frmPolizas.frm"]
    VB6 -- "CreateObject (COM)" --> DLL["Pacifico.Tarificador.dll<br/>.NET Framework 4.8"]
    VB6 -- "ADO + SQL concatenado" --> DB[("SQL Server<br/>Seguros")]
    VB6 -- "Shell dtexec (sin resultado)" --> SSIS["SSIS<br/>CargaPolizas.dtsx"]
    FS["\\\\fileserver\\entrada\\*.csv"] --> SSIS
    SSIS --> DB
```

## Arquitectura objetivo (Azure)

```mermaid
flowchart LR
    U[Usuario / otros sistemas] --> API["API .NET 10<br/>contenedor Linux"]
    API -- "SqlClient parametrizado" --> SQL[("Azure SQL<br/>Seguros")]
    API -- "REST ARM createRun / pipelineruns<br/>(Entra ID, identidad administrada)" --> ADF["Azure Data Factory<br/>PL_CargaPolizas"]
    BLOB["Blob Storage<br/>contenedor entrada"] --> ADF
    ADF --> SQL
    KV["Key Vault"] -. secretos .-> ADF
```

- **Tarificador**: la lógica del componente COM pasa al proyecto `Pacifico.Polizas.Dominio` (sin COM, sin Windows).
- **ETL**: el paquete SSIS se convierte con `tools/ssis2adf` a un pipeline de ADF (Script → Copy → Stored Procedure, con rama de error y `Fail`).
- **Invocación**: la API llama al API REST de ADF y expone el estado de la carga y de cada actividad (`GET /api/cargas/{runId}`), en vez de lanzar `dtexec` sin ver el resultado.
- **Contenedor**: dónde corre (AKS, Container Apps, App Service) queda pendiente de las especificaciones del cliente. La imagen es estándar (`mcr.microsoft.com/dotnet/aspnet:10.0`, usuario no root, puerto 8080).

## Entorno local de la POC (`docker-compose.yml`)

```mermaid
flowchart LR
    DEMO["scripts/demo.sh / curl"] --> API["api :8080<br/>.NET 10"]
    API --> SQL[("sqlserver :1433<br/>SQL Server 2022")]
    API -- "mismo API REST ARM" --> EMU["adf-emulador :5080<br/>.NET 10"]
    EMU -- "una factoría por sistema<br/>sistemas/&lt;id&gt;/adf (formato Git)" --> JSON["sistemas/*/adf"]
    EMU -- "Blob: sistemas/&lt;id&gt;/datos/blob" --> CSV["CSV"]
    EMU --> SQL
    INIT["db-init"] -- "sistemas/*/fuentes/db/*.sql" --> SQL
```

Para pasar a Azure **no cambia el código de la API**, solo su configuración:

| Variable | Local | Azure |
|---|---|---|
| `DataFactory__BaseUrl` | `http://adf-emulador:8080` | `https://management.azure.com` (por defecto) |
| `DataFactory__UsarAzureAd` | `false` | `true` (por defecto): `DefaultAzureCredential` |
| `DataFactory__SubscriptionId` / `ResourceGroup` / `FactoryName` | valores de prueba | los de la factoría real |
| `ConnectionStrings__Seguros` | SQL Server del compose | Azure SQL (idealmente con identidad administrada) |

La identidad de la API necesita el rol **Data Factory Contributor** (o un rol propio con `pipelines/createRun/action` y lectura de `pipelineruns`) sobre la factoría.

## Qué emula y qué no el emulador de ADF

| Emula | No emula (o simplifica) |
|---|---|
| Rutas y formato del API REST: `createRun`, `pipelineruns/{id}`, `queryActivityruns`, `pipelines`; varias factorías (una por sistema) | Autenticación (acepta cualquier solicitud) |
| Actividades `Script`, `SqlServerStoredProcedure`, `Copy` (DelimitedText o tabla/consulta SQL → AzureSqlTable), `ExecutePipeline`, `Fail`, `Wait` | Mapping Data Flows, ForEach, If, Lookup y demás actividades |
| Condiciones `Succeeded`/`Failed`/`Completed`/`Skipped` y la regla de estado final por actividades hoja (con Skipped se evalúa el padre) | Reintentos, timeouts y concurrencia de la factoría |
| Parámetros de pipeline y de dataset; expresiones `pipeline()`, `dataset()`, `activity()`, `concat`, `if`, `empty`, `utcNow`, `formatDateTime`, `convertFromUtc`… | El resto del lenguaje de expresiones |
| Key Vault (secretos desde variables `KeyVault__<secreto>`) y Blob Storage (carpeta local) | Integration Runtime, red privada, triggers |
| Mensajes de error con el formato de ADF (aproximado) | Códigos de error exactos de cada conector |

La validación final del pipeline se hace publicándolo en una factoría real (los JSON de `sistemas/<id>/adf/` se importan tal cual con la integración Git de ADF).

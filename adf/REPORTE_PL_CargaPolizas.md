# Conversión SSIS → ADF: CargaPolizas

Origen: `legacy/ssis/CargaPolizas.dtsx` · Pipeline generado: `pipeline/PL_CargaPolizas.json`

| SSIS | ADF | Nota |
|---|---|---|
| Variable User::FechaProceso = `(DT_DBDATE)GETDATE()` | Parámetro del pipeline `FechaProceso`; si viene vacío se usa la fecha de hoy en hora de Chile |  |
| Conexión OLTP (OLEDB) | Linked service LS_SQL_OLTP (AzureSqlDatabase) | Cadena de conexión en Key Vault; se eliminan las credenciales del paquete |
| Execute SQL: Truncar Staging | Script (NonQuery) |  |
| Conexión ArchivoPolizas (FLATFILE) `\\fileserver\entrada\polizas.csv` | Linked service LS_Blob_ArchivoPolizas + dataset DS_ArchivoPolizas (DelimitedText) | La carpeta compartida pasa a Blob Storage (contenedor `entrada`); el archivo llega por parámetro |
| Data Flow: Cargar CSV a Staging (Origen CSV, Convertir tipos, Buscar Cliente, Destino Staging) | Copy DS_ArchivoPolizas → DS_stg_Polizas | Data Conversion → conversión implícita a los tipos de la tabla destino; ver advertencias |
| Execute SQL: Consolidar (`EXEC dbo.usp_ConsolidarPolizas ?`) | SqlServerStoredProcedure `[dbo].[usp_ConsolidarPolizas]` | Parámetros posicionales (?) → por nombre: FechaProceso |
| Execute SQL: Registrar Error | Script (NonQuery) |  |
| Precedencia Truncar Staging → Cargar CSV a Staging (Success) | dependsOn Succeeded |  |
| Precedencia Cargar CSV a Staging → Consolidar (Success) | dependsOn Succeeded |  |
| Precedencia Consolidar → Registrar Error (Failure) | dependsOn Failed |  |
| Rama de error de Consolidar | Fail `Fallar tras Registrar Error` | Mantiene la semántica de SSIS: sin esto ADF reportaría Succeeded (patrón try-catch) |

## Requiere revisión

- `User::FechaProceso` = `(DT_DBDATE)GETDATE()`: GETDATE() usa la hora local del servidor y utcNow() la hora UTC. Se convierte a hora de Chile (Pacific SA Standard Time) para no cambiar de día en cargas nocturnas
- Data Flow `Cargar CSV a Staging`: el componente `Buscar Cliente` (Microsoft.Lookup) no tiene equivalente en una Copy activity. Opciones: Mapping Data Flow, o mover la lógica al SP que consume el staging (consulta: `SELECT IdCliente, Rut FROM dbo.Clientes`)
- `Registrar Error` usa GETDATE(): en Azure SQL Database devuelve hora UTC, no la hora local del servidor on-premise

## Secretos esperados en Key Vault

- `blob-entrada-connstring`
- `sql-oltp-connstring`

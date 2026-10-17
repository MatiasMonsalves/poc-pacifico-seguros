# Conversión SSIS → ADF: Maestro_Siniestros

Origen: `Maestro_Siniestros.dtsx` · Pipeline generado: `pipeline/PL_Maestro_Siniestros.json`

| SSIS | ADF | Nota |
|---|---|---|
| Execute Package: Ejecutar carga (`Carga_Siniestros.dtsx`) | ExecutePipeline `PL_Carga_Siniestros` | waitOnCompletion = true, como Execute Package |
| Conexión DW (OLEDB) | Linked service LS_SQL_DW (AzureSqlDatabase) | Cadena de conexión en Key Vault; se eliminan las credenciales del paquete |
| Execute SQL: Calcular reservas (`EXEC dbo.usp_CalcularReservas ?`) | SqlServerStoredProcedure `[dbo].[usp_CalcularReservas]` | Parámetros posicionales (?) → por nombre: FechaCorte |
| Send Mail: Avisar falla | Wait (marcador) | **Revisar manualmente** |
| Variable User::FechaCorte = `(DT_DBDATE)GETDATE()` | Parámetro del pipeline `FechaCorte`; si viene vacío se usa la fecha de hoy en Pacific SA Standard Time |  |
| Precedencia Ejecutar carga → Calcular reservas (Success) | dependsOn Succeeded |  |
| Precedencia Calcular reservas → Avisar falla (Failure) | dependsOn Failed |  |
| Rama de error de Calcular reservas | Fail `Fallar tras Avisar falla` | Mantiene la semántica de SSIS: sin esto ADF reportaría Succeeded (patrón try-catch) |

## Requiere revisión

- Tarea `Avisar falla` (Send Mail): sin conversión automática. Se dejó un Wait como marcador
- `User::FechaCorte` = `(DT_DBDATE)GETDATE()`: GETDATE() usa la hora local del servidor y utcNow() la hora UTC. Se convierte a Pacific SA Standard Time para no cambiar de día en cargas nocturnas

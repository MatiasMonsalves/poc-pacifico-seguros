# Conversión SSIS → ADF: Carga_Siniestros

Origen: `Carga_Siniestros.dtsx` · Pipeline generado: `pipeline/PL_Carga_Siniestros.json`

| SSIS | ADF | Nota |
|---|---|---|
| Conexión DW (OLEDB) | Linked service LS_SQL_DW (AzureSqlDatabase) | Cadena de conexión en Key Vault; se eliminan las credenciales del paquete |
| Execute SQL: Limpiar staging | Script (NonQuery) |  |
| Conexión CORE (OLEDB) | Linked service LS_SQL_CORE (AzureSqlDatabase) | Cadena de conexión en Key Vault; se eliminan las credenciales del paquete |
| Data Flow: Extraer siniestros del core (Movimientos vigentes, Convertir montos, Staging siniestros) | Copy DS_CORE_dbo_consulta_Extraer_siniestros_del_core → DS_DW_stg_Siniestros (consulta SQL) | Data Conversion → conversión implícita a los tipos de la tabla destino; Columnas mapeadas por nombre |
| Script Task: Validar totales | Wait (marcador) | **Revisar manualmente** |
| Precedencia Limpiar staging → Extraer siniestros del core (Success) | dependsOn Succeeded |  |
| Precedencia Extraer siniestros del core → Validar totales (Success) | dependsOn Succeeded |  |

## Requiere revisión

- Tarea `Validar totales` (Script Task): contiene código C#/VB: reescribir como Azure Function, Batch o lógica en SQL. Se dejó un Wait como marcador

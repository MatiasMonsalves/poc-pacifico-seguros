# Equivalencias SSIS → Azure Data Factory

## Flujo de control

| SSIS | ADF | Notas |
|---|---|---|
| Package | Pipeline | Los parámetros del paquete pasan a ser parámetros del pipeline |
| Execute SQL Task | Script activity / Stored Procedure activity | `?` (parámetros OLE DB) → `@{pipeline().parameters.x}` o parámetros con nombre |
| Data Flow Task | Copy activity (si no transforma) / Mapping Data Flow | Preferir Copy + SP cuando la lógica ya está en T-SQL |
| Execute Package Task | Execute Pipeline activity | |
| Sequence Container | Agrupación lógica (sin equivalente directo) | Se aplana o se lleva a un sub-pipeline |
| Foreach Loop (archivos) | Get Metadata + ForEach | |
| For Loop | Until activity | |
| Script Task | Azure Function / Batch / contenedor (Web activity) | **Riesgo**: hay que reescribir el código |
| File System Task | Copy / Delete activity sobre Blob o ADLS | Las rutas UNC se reemplazan por storage |
| FTP Task | Copy activity con linked service FTP/SFTP | |
| Send Mail Task | Logic App llamada desde Web activity | |
| Precedence: Success / Failure / Completion | Dependency: Succeeded / Failed / Completed | Las expresiones pasan a una If Condition |
| Variables / expresiones | Variables del pipeline + lenguaje de expresiones de ADF | `GETDATE()` → `@utcNow()` |
| SQL Agent Job (schedule) | Trigger (schedule / tumbling window / evento de storage) | |
| Connection Manager | Linked Service + Key Vault para los secretos | |
| Event handlers / logging | Dependencias "On failure" + Log Analytics | |

## Componentes de Data Flow

| SSIS | Mapping Data Flow |
|---|---|
| OLE DB / ADO.NET Source | Source (dataset SQL) |
| Flat File Source | Source (DelimitedText en Blob/ADLS) |
| Derived Column | Derived Column |
| Data Conversion | Cast / Derived Column |
| Lookup | Lookup |
| Conditional Split | Conditional Split |
| Union All / Merge | Union |
| Merge Join | Join |
| Aggregate | Aggregate |
| Sort | Sort |
| Slowly Changing Dimension | Alter Row + Exists/Lookup |
| OLE DB Command (por fila) | Alter Row + Sink, o carga a staging + SP basado en conjuntos |
| OLE DB Destination | Sink |

## Alternativa de transición
**Azure-SSIS Integration Runtime** permite ejecutar los `.dtsx` sin cambios dentro de ADF (lift & shift). Sirve como plan B o como paso intermedio, pero no moderniza nada; para la POC se recomienda la reescritura nativa de al menos un paquete.

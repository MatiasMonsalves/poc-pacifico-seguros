# Conversión SSIS → ADF

| Paquete | Pipeline | Actividades | Sin convertir | Advertencias |
|---|---|---|---|---|
| `Carga_Siniestros.dtsx` | [PL_Carga_Siniestros](REPORTE_PL_Carga_Siniestros.md) | 3 | 1 | 1 |
| `Maestro_Siniestros.dtsx` | [PL_Maestro_Siniestros](REPORTE_PL_Maestro_Siniestros.md) | 4 | 1 | 2 |

## Secretos esperados en Key Vault

- `siniestros-sql-core-connstring`
- `siniestros-sql-dw-connstring`

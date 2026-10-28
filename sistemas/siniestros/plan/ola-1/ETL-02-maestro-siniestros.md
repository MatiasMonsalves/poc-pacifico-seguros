# ETL-02 Maestro_Siniestros (SSIS → ADF)

- Épica: ETL · Estado: parcial: 1 marcador(es) por migrar
- Paquete: `ssis_pkg:maestro_siniestros` — `ssis/Maestro_Siniestros.dtsx` (vb6graph)
- Pipeline generado: `adf/pipeline/PL_Maestro_Siniestros.json` (tools/ssis2adf)

## Pendiente de migrar a mano

- PL_Maestro_Siniestros: Avisar falla (Send Mail)

## Criterios de aceptación de paridad

- Mismo archivo/origen de entrada → mismas filas en las tablas destino que el paquete SSIS.
- Misma rama de error: la falla registra el error y deja el pipeline en Failed (actividad Fail).

## Pruebas

- validar_adf;emulador ADF (scripts/demo)

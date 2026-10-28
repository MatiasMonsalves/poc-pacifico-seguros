# ETL-01 CargaPolizas (SSIS → ADF)

- Épica: ETL · Estado: convertido
- Paquete: `ssis_pkg:cargapolizas` — `ssis/CargaPolizas.dtsx` (vb6graph)
- Pipeline generado: `adf/pipeline/PL_CargaPolizas.json` (tools/ssis2adf)

## Pendiente de migrar a mano

- Nada: todas las tareas del paquete se convirtieron

## Criterios de aceptación de paridad

- Mismo archivo/origen de entrada → mismas filas en las tablas destino que el paquete SSIS.
- Misma rama de error: la falla registra el error y deja el pipeline en Failed (actividad Fail).

## Pruebas

- validar_adf;emulador ADF (scripts/demo)

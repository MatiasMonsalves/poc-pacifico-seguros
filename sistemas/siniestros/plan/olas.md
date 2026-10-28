# Olas: Siniestros

Generado desde el grafo de vb6graph y los resultados de la fábrica. Alcance acotado de la POC: una ola piloto.

## Ola 1 (piloto)

| Tarea | Origen legado | Estado |
|---|---|---|
| [ETL-01](ola-1/ETL-01-carga-siniestros.md) | `ssis_pkg:carga_siniestros` | parcial: 1 marcador(es) por migrar |
| [ETL-02](ola-1/ETL-02-maestro-siniestros.md) | `ssis_pkg:maestro_siniestros` | parcial: 1 marcador(es) por migrar |

## Propiedad de escritura por tabla (coexistencia)

| Tabla | Escribe hoy | Lee |
|---|---|---|
| `db_proc:dbo.usp_calcularreservas` | — | — |
| `table:dbo.siniestro_mov` | — | ssis:movimientos vigentes |
| `table:stg.siniestros` | ssis:limpiar staging, ssis:staging siniestros | — |

## Fuera de alcance (código muerto, confirmar en R3)

- Nada

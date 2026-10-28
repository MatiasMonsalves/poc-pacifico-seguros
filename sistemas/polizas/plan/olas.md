# Olas: Pólizas

Generado desde el grafo de vb6graph y los resultados de la fábrica. Alcance acotado de la POC: una ola piloto.

## Ola 1 (piloto)

| Tarea | Origen legado | Estado |
|---|---|---|
| [POL-01](ola-1/POL-01-form-load.md) | `proc:polizas/frmpolizas.form_load` | hecho |
| [POL-02](ola-1/POL-02-cmdbuscar-click.md) | `proc:polizas/frmpolizas.cmdbuscar_click` | hecho |
| [POL-03](ola-1/POL-03-cmdcotizar-click.md) | `proc:polizas/frmpolizas.cmdcotizar_click` | hecho |
| [POL-04](ola-1/POL-04-cmdrecalcular-click.md) | `proc:polizas/frmpolizas.cmdrecalcular_click` | hecho |
| [POL-05](ola-1/POL-05-cmdcargar-click.md) | `proc:polizas/frmpolizas.cmdcargar_click` | hecho |
| [ETL-01](ola-1/ETL-01-cargapolizas.md) | `ssis_pkg:cargapolizas` | convertido |

## Propiedad de escritura por tabla (coexistencia)

| Tabla | Escribe hoy | Lee |
|---|---|---|
| `db_proc:dbo.usp_consolidarpolizas` | — | — |
| `db_proc:dbo.usp_recalcularprimas` | — | — |
| `table:dbo.clientes` | — | ssis:buscar cliente, vb6:frmpolizas.cmdcotizar_click |
| `table:dbo.polizas` | — | vb6:frmpolizas.cmdbuscar_click, vb6:frmpolizas.exportarexcelviejo |
| `table:log.erroresetl` | ssis:registrar error | — |
| `table:stg.polizas` | ssis:destino staging, ssis:truncar staging | — |

## Fuera de alcance (código muerto, confirmar en R3)

- `proc:polizas/frmpolizas.exportarexcelviejo` — vb6/frmPolizas.frm:72-75
- `proc:polizas/modconexion.formatearrutviejo` — vb6/modConexion.bas:19-21

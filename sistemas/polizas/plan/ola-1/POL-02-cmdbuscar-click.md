# POL-02 frmPolizas.cmdBuscar_Click

- Épica: frmPolizas (Ola 1) · Estado: hecho · Complejidad ciclomática: 1
- Evidencia: `proc:polizas/frmpolizas.cmdbuscar_click` — `vb6/frmPolizas.frm:40-45` (vb6graph)

## Contexto en el legado

- SQL (SELECT) línea 42: `SELECT NumPoliza, TipoSeguro, Prima, Estado FROM dbo.Polizas WHERE IdCliente = {?}`

## Datos

| Tabla | Modo |
|---|---|
| Polizas | READ |

## Destino

- Generado por vb62net: `/api/polizas/buscar` (Automático)
- App terminada: app: GET /api/clientes/{idCliente}/polizas

## Criterios de aceptación de paridad

- Mismos datos de entrada → mismo resultado que el VB6 (y que el componente COM, si aplica).
- Mismas validaciones y mensajes de error equivalentes.

## Pruebas

- scripts/demo (punta a punta);cobertura

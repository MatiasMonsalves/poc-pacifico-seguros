# POL-04 frmPolizas.cmdRecalcular_Click

- Épica: frmPolizas (Ola 1) · Estado: hecho · Complejidad ciclomática: 1
- Evidencia: `proc:polizas/frmpolizas.cmdrecalcular_click` — `vb6/frmPolizas.frm:62-69` (vb6graph)

## Contexto en el legado

- SQL (EXEC) línea 66: `EXEC dbo.usp_RecalcularPrimas`

## Datos

| Tabla | Modo |
|---|---|
| usp_RecalcularPrimas | READ |

## Destino

- Generado por vb62net: `/api/polizas/recalcular` (Automático)
- App terminada: app: POST /api/primas/recalcular

## Criterios de aceptación de paridad

- Mismos datos de entrada → mismo resultado que el VB6 (y que el componente COM, si aplica).
- Mismas validaciones y mensajes de error equivalentes.

## Pruebas

- scripts/demo (punta a punta);cobertura

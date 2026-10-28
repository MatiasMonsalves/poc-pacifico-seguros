# POL-03 frmPolizas.cmdCotizar_Click

- Épica: frmPolizas (Ola 1) · Estado: hecho · Complejidad ciclomática: 1
- Evidencia: `proc:polizas/frmpolizas.cmdcotizar_click` — `vb6/frmPolizas.frm:48-60` (vb6graph)

## Contexto en el legado

- SQL (SELECT) línea 54: `SELECT FechaNacimiento FROM dbo.Clientes WHERE IdCliente = {?}`
- Llama a: CalcularEdad
- Llamada sin resolver (enlace tardío/COM): tarificador.calcularprima (vb6/frmPolizas.frm:58)

## Datos

| Tabla | Modo |
|---|---|
| Clientes | READ |

## Destino

- Generado por vb62net: `/api/polizas/cotizar` (Parcial)
- App terminada: app: POST /api/cotizaciones

## Criterios de aceptación de paridad

- Mismos datos de entrada → mismo resultado que el VB6 (y que el componente COM, si aplica).
- Mismas validaciones y mensajes de error equivalentes.

## Pruebas

- ParidadLegadoTests;TarificadorTests;EdadTests

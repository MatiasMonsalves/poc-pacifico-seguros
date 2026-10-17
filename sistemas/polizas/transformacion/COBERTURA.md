# Cobertura VB6 → .NET 10

5 de 5 eventos VB6 tienen reemplazo en la app terminada.

| Evento VB6 | Generado por vb62net | App terminada |
|---|---|---|
| `frmPolizas.Form_Load` | Automático → `/api/polizas/catalogos` | `GET /api/catalogos` |
| `frmPolizas.cmdBuscar_Click` | Automático → `/api/polizas/buscar` | `GET /api/clientes/{idCliente}/polizas` |
| `frmPolizas.cmdCotizar_Click` | Parcial → `/api/polizas/cotizar` | `POST /api/cotizaciones` |
| `frmPolizas.cmdRecalcular_Click` | Automático → `/api/polizas/recalcular` | `POST /api/primas/recalcular` |
| `frmPolizas.cmdCargar_Click` | Automático → `/api/polizas/cargar` | `POST /api/cargas` |

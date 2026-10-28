# Transformación VB6 → .NET 10: Polizas.vbp

Proyecto generado: `Polizas.Generado/` (`dotnet build` / `docker build`). Estado por procedimiento:

- **Automático**: traducido y funcional.
- **Parcial**: el acceso a datos está traducido; falta lógica que no es mecánica (responde 501).
- **Pendiente**: requiere migración manual (responde 501 o lanza excepción).
- **Reemplazado**: la infraestructura VB6 la cubre .NET (conexiones, configuración).
- **Fuera de alcance**: código muerto según vb6graph; no se migra (confirmar con usuarios, checkpoint R3).

| VB6 | Evidencia (vb6graph) | Destino .NET 10 | Estado | SQL / SP / ADF / COM | Notas |
|---|---|---|---|---|---|
| `frmPolizas.Form_Load` | `vb6/frmPolizas.frm:32-37` | `/api/polizas/catalogos` | Automático | Catálogo cboTipo |  |
| `frmPolizas.cmdBuscar_Click` | `vb6/frmPolizas.frm:40-45` | `/api/polizas/buscar` | Automático | SQL `SELECT NumPoliza, TipoSeguro, Prima, Estado FROM dbo.Polizas WHERE IdCliente = @Cliente` | El SQL original se armaba concatenando texto del usuario (inyección SQL); el generado está parametrizado |
| `frmPolizas.cmdCotizar_Click` | `vb6/frmPolizas.frm:48-60` | `/api/polizas/cotizar` | Parcial | SQL `SELECT FechaNacimiento FROM dbo.Clientes WHERE IdCliente = @Cliente`<br>COM `PacificoTarificador.Tarificador` | El SQL original se armaba concatenando texto del usuario (inyección SQL); el generado está parametrizado |
| `frmPolizas.cmdRecalcular_Click` | `vb6/frmPolizas.frm:62-69` | `/api/polizas/recalcular` | Automático | SP `dbo.usp_RecalcularPrimas` |  |
| `frmPolizas.ExportarExcelViejo` | `vb6/frmPolizas.frm:72-75` | `— (no se migra)` | Fuera de alcance | SQL `SELECT * FROM dbo.Polizas WHERE Estado = 'VIGENTE'` | Código muerto según vb6graph (seguro de borrar) |
| `frmPolizas.cmdCargar_Click` | `vb6/frmPolizas.frm:78-83` | `/api/polizas/cargar` | Automático | ADF `PL_CargaPolizas` (desde `CargaPolizas.dtsx`) | MsgBox se devuelve como respuesta JSON |
| `modConexion.AbrirConexion` | `vb6/modConexion.bas:8-12` | `Db (inyección de SqlConnection)` | Reemplazado | — | Conexión ADODB con credenciales en el código → cadena de conexión por configuración/Key Vault |
| `modConexion.CalcularEdad` | `vb6/modConexion.bas:14-16` | `modConexion.CalcularEdad` | Automático | — | DateDiff de VB6 cuenta cambios de período, no tiempo transcurrido; Vb6.DateDiff conserva ese comportamiento |
| `modConexion.FormatearRutViejo` | `vb6/modConexion.bas:19-21` | `— (no se migra)` | Fuera de alcance | — | Código muerto según vb6graph (seguro de borrar) |

**Resumen:** 5 automático, 1 parcial, 0 pendiente, 1 reemplazado, 2 fuera de alcance

Siguiente paso: completar lo parcial/pendiente (en `sistemas/polizas/app` está el resultado terminado de este ejemplo) y validar con pruebas de paridad contra el sistema legado.

## Contraste con vb6graph (dos parsers independientes)

vb6graph (tree-sitter) y vb62net coinciden en **9** procedimientos.

- Llamada sin resolver (enlace tardío/COM) en `frmPolizas.cmdCotizar_Click`: tarificador.calcularprima (vb6/frmPolizas.frm:58)

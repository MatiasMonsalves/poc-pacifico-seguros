# Transformación VB6 → .NET 10: Polizas.vbp

Proyecto generado: `Polizas.Generado/` (`dotnet build` / `docker build`). Estado por procedimiento:

- **Automático**: traducido y funcional.
- **Parcial**: el acceso a datos está traducido; falta lógica que no es mecánica (responde 501).
- **Pendiente**: requiere migración manual (responde 501 o lanza excepción).
- **Reemplazado**: la infraestructura VB6 la cubre .NET (conexiones, configuración).

| VB6 | Destino .NET 10 | Estado | SQL / SP / ADF / COM | Notas |
|---|---|---|---|---|
| `frmPolizas.Form_Load` | `/api/polizas/catalogos` | Automático | Catálogo cboTipo |  |
| `frmPolizas.cmdBuscar_Click` | `/api/polizas/buscar` | Automático | SQL `SELECT NumPoliza, TipoSeguro, Prima, Estado FROM dbo.Polizas WHERE IdCliente = @Cliente` | El SQL original se armaba concatenando texto del usuario (inyección SQL); el generado está parametrizado |
| `frmPolizas.cmdCotizar_Click` | `/api/polizas/cotizar` | Parcial | SQL `SELECT FechaNacimiento FROM dbo.Clientes WHERE IdCliente = @Cliente`<br>COM `PacificoTarificador.Tarificador` | El SQL original se armaba concatenando texto del usuario (inyección SQL); el generado está parametrizado |
| `frmPolizas.cmdRecalcular_Click` | `/api/polizas/recalcular` | Automático | SP `dbo.usp_RecalcularPrimas` |  |
| `frmPolizas.cmdCargar_Click` | `/api/polizas/cargar` | Automático | ADF `PL_CargaPolizas` (desde `CargaPolizas.dtsx`) | MsgBox se devuelve como respuesta JSON |
| `modConexion.AbrirConexion` | `Db (inyección de SqlConnection)` | Reemplazado | — | Conexión ADODB con credenciales en el código → cadena de conexión por configuración/Key Vault |
| `modConexion.CalcularEdad` | `modConexion.CalcularEdad` | Automático | — | DateDiff de VB6 cuenta cambios de período, no tiempo transcurrido; Vb6.DateDiff conserva ese comportamiento |

**Resumen:** 5 automático, 1 parcial, 0 pendiente, 1 reemplazado

Siguiente paso: completar lo parcial/pendiente (en `sistemas/polizas/app` está el resultado terminado de este ejemplo) y validar con pruebas de paridad contra el sistema legado.

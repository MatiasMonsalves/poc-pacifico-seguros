# Hallazgos: Siniestros

Generado con `python tools/portafolio/portafolio.py analizar --solo siniestros --decompilar`; ver también [RESUMEN.md](RESUMEN.md).

## Componente `Pacifico.Siniestros.Reglas.dll` (solo binario, .NET Framework 4.0)

REA (`rea/BINARIOS.md`) identificó la clase `CalculadoraReserva`, su acceso a datos con `SqlClient`, una consulta SQL embebida y una cadena de conexión con credenciales. La decompilación de ILSpy quedó importada en REA y anclada al binario (2 métodos).

| # | Hallazgo | Dónde | Impacto |
|---|---|---|---|
| S1 | **Regla de reserva duplicada e inconsistente**: el componente aplica el recargo de 10 % con más de **60** días abiertos; `usp_CalcularReservas` lo aplica con más de **90** | DLL vs SP | Un siniestro de 61 a 90 días tiene una reserva distinta en el reporte WinForms y en la BD |
| S2 | Credenciales en el binario (`User ID=reglas;Password=…`) y en `Web.config` | DLL, Web.config | Seguridad: pasar a Key Vault / identidad administrada |
| S3 | SQL armado concatenando texto en `ServicioSiniestros.SiniestrosPorPoliza` | ASMX | Inyección SQL |

## Aplicaciones .NET

| Proyecto | Ruta propuesta |
|---|---|
| `Siniestros.Web` (ASMX, .NET 3.5, LINQ to SQL) | API REST ASP.NET Core en .NET 10 (o CoreWCF si hay consumidores SOAP que no pueden cambiar) |
| `Siniestros.Reportes` (WinForms, .NET 4.0, Crystal Reports) | Definir con el negocio: reporte web (SSRS/Power BI/PDF) o WinForms en .NET 10 solo Windows |

## ETL

`Maestro_Siniestros` y `Carga_Siniestros` se convirtieron a `PL_Maestro_Siniestros` (Execute Pipeline) y `PL_Carga_Siniestros` (Script + Copy tabla→tabla). Quedan dos marcadores por migrar a mano:

- **Validar totales** (Script Task): reescribir como consulta de validación en SQL (Script activity o SP que lance error) o como Azure Function.
- **Avisar falla** (Send Mail): Logic App o Web activity a un servicio de correo; ADF también puede alertar desde Azure Monitor.

Ambos pipelines se ejecutaron en el emulador (`scripts/demo.sh`).

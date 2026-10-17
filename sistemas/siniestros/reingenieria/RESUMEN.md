# Siniestros (`siniestros`)

Extracción de siniestros desde el core, cálculo de reservas (SSIS maestro/hijo), web service ASMX .NET 3.5 y reportes WinForms con Crystal Reports.

**Complejidad: Media** (puntaje 37.5) · Criticidad: Media · Estado: Analizado y convertido a ADF

Tecnologías: .NET Framework v3.5, .NET Framework v4.0, SSIS, T-SQL · BDs: CoreLegado, Siniestros

| Métrica | Valor |
|---|---|
| Paquetes SSIS / tareas | 2 / 6 |
| Pipelines ADF generados | 2 (2 actividades sin convertir, 3 advertencias) |
| Objetos de BD | 4 |
| Proyectos VB6/.NET | 2 |
| Binarios analizados con REA | 1 (0 nativos/VB6) |

## Proyectos

| Proyecto | Tipo | Framework | Esfuerzo | Ruta sugerida |
|---|---|---|---|---|
| `dotnet/Siniestros.Reportes/Siniestros.Reportes.csproj` | WinForms | v4.0 | Medio | WinForms en .NET 10 (solo Windows, no contenedor Linux) o reescribir como web |
| `dotnet/Siniestros.Web/Siniestros.Web.csproj` | Servicio ASMX | v3.5 | Alto | API REST en ASP.NET Core; CoreWCF si los consumidores exigen SOAP |

## Binarios

| Binario | Tipo | Siguiente paso |
|---|---|---|
| `Pacifico.Siniestros.Reglas.dll` | .NET Framework .NETFramework,Version=v4.0 | Leer la decompilación, migrar las reglas y validarlas con pruebas de paridad contra este binario |

## Actividades ADF sin conversión automática

- PL_Carga_Siniestros: Validar totales (Script Task)
- PL_Maestro_Siniestros: Avisar falla (Send Mail)

## Riesgos

- dotnet/Siniestros.Reportes/Siniestros.Reportes.csproj: Crystal Reports: no tiene versión para .NET moderno en Linux; evaluar SSRS, Power BI o una librería de PDF
- dotnet/Siniestros.Web/Siniestros.Web.csproj: LINQ to SQL: no existe en .NET 10; migrar a EF Core o SqlClient
- dotnet/Siniestros.Web/Siniestros.Web.csproj: Servicios ASMX: no existen en .NET 10
- dotnet/Siniestros.Web/Siniestros.Web.csproj: .NET Framework v3.5 (CLR 2): el salto a .NET 10 es mayor; revisar APIs obsoletas

## Advertencias de la conversión a ADF

- PL_Carga_Siniestros: Tarea `Validar totales` (Script Task): contiene código C#/VB: reescribir como Azure Function, Batch o lógica en SQL. Se dejó un Wait como marcador
- PL_Maestro_Siniestros: Tarea `Avisar falla` (Send Mail): sin conversión automática. Se dejó un Wait como marcador
- PL_Maestro_Siniestros: `User::FechaCorte` = `(DT_DBDATE)GETDATE()`: GETDATE() usa la hora local del servidor y utcNow() la hora UTC. Se convierte a Pacific SA Standard Time para no cambiar de día en cargas nocturnas

## Detalle

- [Inventario](inventario/inventario.md)
- [Binarios (REA)](rea/BINARIOS.md)
- [Conversión a ADF](../adf/REPORTE_CONVERSION.md)

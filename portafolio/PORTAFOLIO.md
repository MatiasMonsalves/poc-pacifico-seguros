# Portafolio de sistemas legados

Generado el 28-10-2026 con `tools/portafolio`.

| Sistema | Tecnologías | Paquetes SSIS | Proyectos | Binarios | Sin convertir | Riesgos | Complejidad |
|---|---|---|---|---|---|---|---|
| [Pólizas](../sistemas/polizas/reingenieria/RESUMEN.md) | SSIS, T-SQL, VB6 | 1 | 1 | 1 | 0 | 1 | Media (22.5) |
| [Siniestros](../sistemas/siniestros/reingenieria/RESUMEN.md) | .NET Framework v3.5, .NET Framework v4.0, SSIS, T-SQL | 2 | 2 | 1 | 2 | 4 | Media (37.5) |

## Orden sugerido

De menor a mayor complejidad: los primeros sistemas sirven para ajustar la fábrica (convertidor, emulador, pruebas de paridad) antes de abordar los más riesgosos. La criticidad de negocio puede cambiar este orden.

1. **Pólizas**: media
2. **Siniestros**: media; atención: PL_Carga_Siniestros: Validar totales (Script Task)

## Bases de datos compartidas

- Ninguna detectada en las cadenas de conexión

## Riesgos transversales

- (1 sistema) Compilado a código nativo: si falta el fuente, del ejecutable solo se obtiene pseudocódigo (REA + Ghidra/IDA)
- (1 sistema) Servicios ASMX: no existen en .NET 10
- (1 sistema) .NET Framework v3.5 (CLR 2): el salto a .NET 10 es mayor; revisar APIs obsoletas
- (1 sistema) Crystal Reports: no tiene versión para .NET moderno en Linux; evaluar SSRS, Power BI o una librería de PDF
- (1 sistema) LINQ to SQL: no existe en .NET 10; migrar a EF Core o SqlClient

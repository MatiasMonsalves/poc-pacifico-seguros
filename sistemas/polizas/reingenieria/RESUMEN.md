# Pólizas (`polizas`)

Mantenedor y cotización de pólizas (VB6 + componente COM .NET 4.8) y carga diaria de pólizas desde archivo (SSIS).

**Complejidad: Media** (puntaje 22.5) · Criticidad: Alta · Estado: POC construida (app .NET 10 + ADF)

Tecnologías: SSIS, T-SQL, VB6 · BDs: Seguros

| Métrica | Valor |
|---|---|
| Paquetes SSIS / tareas | 1 / 4 |
| Pipelines ADF generados | 1 (0 actividades sin convertir, 3 advertencias) |
| Objetos de BD | 6 |
| Proyectos VB6/.NET | 1 |
| Binarios analizados con REA | 1 (0 nativos/VB6) |

## Proyectos

| Proyecto | Tipo | Framework | Esfuerzo | Ruta sugerida |
|---|---|---|---|---|
| `vb6/Polizas.vbp` | VB6 aplicación con formularios | VB6 runtime (MSVBVM60) | Alto | Reescribir: UI web o API .NET 10; reglas de negocio a una biblioteca .NET 10 |

## Binarios

| Binario | Tipo | Siguiente paso |
|---|---|---|
| `Pacifico.Tarificador.dll` | .NET Framework .NETFramework,Version=v4.8 | Leer la decompilación, migrar las reglas y validarlas con pruebas de paridad contra este binario |

## Riesgos

- vb6/Polizas.vbp: Compilado a código nativo: si falta el fuente, del ejecutable solo se obtiene pseudocódigo (REA + Ghidra/IDA)

## Advertencias de la conversión a ADF

- PL_CargaPolizas: Data Flow `Cargar CSV a Staging`: el componente `Buscar Cliente` (Microsoft.Lookup) no tiene equivalente en una Copy activity. Opciones: Mapping Data Flow, o mover la lógica al SQL de origen o al SP que consume el destino (consulta: `SELECT IdCliente, Rut FROM dbo.Clientes`)
- PL_CargaPolizas: `Registrar Error` usa GETDATE(): en Azure SQL Database devuelve hora UTC, no la hora local del servidor on-premise
- PL_CargaPolizas: `User::FechaProceso` = `(DT_DBDATE)GETDATE()`: GETDATE() usa la hora local del servidor y utcNow() la hora UTC. Se convierte a Pacific SA Standard Time para no cambiar de día en cargas nocturnas

## Detalle

- [Inventario](inventario/inventario.md)
- [Binarios (REA)](rea/BINARIOS.md)
- [Conversión a ADF](../adf/REPORTE_CONVERSION.md)

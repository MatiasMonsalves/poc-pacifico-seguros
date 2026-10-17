# Verificación de la fábrica de migración

Ejecutada el 17-10-2026 11:07 con `scripts/verificar.sh `.

| Paso | Resultado | Log |
|---|---|---|
| 1. Análisis del portafolio (inventario + REA + SSIS→ADF) | OK | `portafolio/logs/analisis.log` |
| 2. Transformación VB6 → .NET 10 (generar y compilar) | OK | `portafolio/logs/vb62net.log` |
| 3. Validación de los pipelines ADF | OK | `portafolio/logs/validar_adf.log` |
| 4. Pruebas unitarias y de paridad (.NET 10) | OK | `portafolio/logs/pruebas.log` |
| 5. Entorno local (docker compose) | OK | `portafolio/logs/compose.log` |
| 6. Pruebas de punta a punta (scripts/demo.sh) | OK | `portafolio/logs/demo.log` |
| 7. Cobertura VB6 → app terminada | OK | `portafolio/logs/cobertura.log` |

## Resultados

- Portafolio: [PORTAFOLIO.md](PORTAFOLIO.md)
- Transformación VB6 → .NET: [sistemas/polizas/transformacion/MAPEO_VB6_NET.md](../sistemas/polizas/transformacion/MAPEO_VB6_NET.md)
- Cobertura: [sistemas/polizas/transformacion/COBERTURA.md](../sistemas/polizas/transformacion/COBERTURA.md)
- SSIS → ADF: [sistemas/polizas/adf/REPORTE_CONVERSION.md](../sistemas/polizas/adf/REPORTE_CONVERSION.md)
- SSIS → ADF: [sistemas/siniestros/adf/REPORTE_CONVERSION.md](../sistemas/siniestros/adf/REPORTE_CONVERSION.md)

### Validación de ADF

```
sistemas/polizas/adf: 1 pipelines, 5 actividades, 2 datasets, 3 linked services · 0 errores, 0 advertencias
sistemas/siniestros/adf: 2 pipelines, 7 actividades, 2 datasets, 3 linked services · 0 errores, 2 advertencias
  AVISO  pipeline/PL_Carga_Siniestros › Validar totales: MARCADOR Script Task: contiene código C#/VB: reescribir como Azure Function, Batch o lógica en SQL
  AVISO  pipeline/PL_Maestro_Siniestros › Avisar falla: MARCADOR Send Mail: sin conversión automática
```

### Punta a punta

```
   OK  Pólizas del cliente 1: POL-0001
   OK  Intento de inyección SQL: 404
   OK  P1 redondeo al par como el legado (AUTO, 23 años, 600 UF): 33.34
   OK  P9 edad estilo VB6 DateDiff (nacido 20-12-2001): 25
   OK  Tipo de seguro inválido: 400
   OK  Estado del pipeline: Succeeded
   OK  Póliza nueva POL-0005 del cliente 5: POL-0005
   OK  Estado del pipeline: Failed
   OK  Se ejecutó Registrar Error: Succeeded
   OK  Estado del pipeline: Failed
   OK  Falla en la copia: Failed
   OK  Estado consultado por runId: Succeeded
   OK  Buscar (SQL parametrizado): POL-0001
   OK  Intento de inyección SQL rechazado: 400
   OK  Cotizar queda pendiente (lógica COM): 501
   OK  Cargar (Shell dtexec → pipeline ADF): Succeeded
   OK  Estado del pipeline maestro: Succeeded
   OK  Filas copiadas de CoreLegado a Siniestros (solo vigentes): 3
   OK  Script Task marcado como pendiente de migrar: True
   Todas las verificaciones pasaron
```

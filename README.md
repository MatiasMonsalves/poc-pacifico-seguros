# POC Pacífico Seguros — Ingeniería inversa y migración a la nube

POC para hacer ingeniería inversa de un sistema legado (ETL **SSIS** + lógica en **T-SQL** + aplicación **VB6/.NET**) y llevarlo a la nube (**Azure Data Factory** + servicio en **Docker**).

- Plan y fases: [`docs/PLAN_POC.md`](docs/PLAN_POC.md)
- Equivalencias SSIS → ADF: [`docs/MAPEO_SSIS_ADF.md`](docs/MAPEO_SSIS_ADF.md)
- Ingeniería inversa de binarios sin fuente (.NET, VB6): [REA](https://github.com/morluto/rea), ver Fase 1 del plan

## Inventario automático

```bash
# Con los fuentes de ejemplo
python3 tools/re_inventario/inventario.py samples salida/samples

# Con los fuentes reales (copiarlos a fuentes/, que no se versiona)
python3 tools/re_inventario/inventario.py fuentes salida/cliente
```

Genera `inventario.md` (paquetes SSIS con diagrama del flujo, objetos T-SQL, SQL embebido en la app y una matriz de dependencias) e `inventario.json`. Las contraseñas de las cadenas de conexión se reemplazan por `****`. Solo usa la librería estándar de Python 3.9+.

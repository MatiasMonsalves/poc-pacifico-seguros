# Integración con vb6graph

[vb6graph](#instalación) (Fabián Rojas, v0.1.0) convierte el VB6 y los paquetes SSIS en un **grafo de conocimiento** (SQLite).
- **Parser:** tree-sitter.
- **Evidencia:** cada nodo y cada arista llevan `archivo:línea`.
- **Salidas:** reporte HTML/CSV, servidor MCP para agentes y una capa de IA opcional.

En la fábrica cumple el rol de **fuente de verdad del assessment**; la fábrica agrega la transformación, la conversión a ADF y la verificación.

| Etapa | Herramienta | Qué toma del grafo |
|---|---|---|
| Assessment | `vb6graph index` + `report` (lo ejecuta `tools/portafolio`) | — (lo produce) |
| VB6 → .NET 10 | `tools/vb62net --grafo` | Excluye el **código muerto**; cita en el código generado el nodo y las líneas de origen; contrasta ambos parsers (procedimientos, SQL y llamadas sin resolver) |
| SSIS → ADF | `tools/ssis2adf` | El linaje de tablas VB6↔SSIS alimenta la propiedad de escritura del plan |
| Plan y trazabilidad | `tools/vb6graph_puente/plan.py` | `plan/trazabilidad.csv`, `plan/olas.md`, tareas `plan/ola-1/*.md` con la plantilla de vb6graph y `plan/AVANCE.md` (% migrado) |

La matriz de trazabilidad con estado por nodo y el % de avance figuran en la documentación de vb6graph como *"propuesto — aún no implementado"*. Aquí se generan cruzando el grafo con los resultados de la fábrica: lo generado por vb62net, la cobertura de la app terminada, los pipelines convertidos y las pruebas declaradas en `sistema.json`.

## Instalación

vb6graph es **opcional**. Sin él, la fábrica reutiliza el grafo guardado en `sistemas/<id>/reingenieria/vb6graph/`, igual que hace con el análisis de REA.

```bash
uv tool install --python 3.12 --with openpyxl ./vb6graph-0.1.0-py3-none-any.whl
vb6graph setup      # compila tree-sitter (necesita un compilador C; si no hay, usa el parser de respaldo) y registra el MCP
vb6graph doctor
```

El paquete lo distribuye Fabián (`vb6graph-portable-0.1.0.zip`) y no está incluido en este repositorio. Según su propia documentación, la instalación en Windows no se ha probado.

## Qué produce para cada sistema

```
sistemas/<id>/reingenieria/vb6graph/
  grafo.db          grafo SQLite (nodos, aristas con evidencia, texto de los fuentes)
  reporte.html      reporte de assessment (resumen, inventario, navegación, tablas, SSIS, riesgos, código muerto)
  csv/              inventario, procedimientos, tablas (dueños de lectura/escritura), riesgos, código muerto, diagnósticos
sistemas/<id>/plan/
  trazabilidad.csv  legacy_node → decisión → tarea → componente nuevo → pruebas → estado → evidencia
  olas.md           ola piloto, propiedad de escritura por tabla, fuera de alcance
  ola-1/*.md        una tarea por evento de formulario y por paquete SSIS
  AVANCE.md         % de nodos en alcance migrados
```

Un paquete SSIS con marcadores (Script Task, Send Mail…) cuenta como **parcial**, no como migrado.

## Mejoras al grafo (parche para el autor)

`tools/vb6graph_puente/parches/` trae dos parches que corrigen tres problemas encontrados al integrarlo. Se aplica a la instalación local con `python tools/vb6graph_puente/aplicar_parche.py` (Windows o Linux, necesita git; es idempotente). Los grafos guardados de `polizas` y `siniestros` ya están generados con el parche.

| | Antes | Con el parche |
|---|---|---|
| Esquema | `TRUNCATE TABLE stg.Polizas` y `SELECT … FROM dbo.Polizas` caían en el mismo nodo `table:polizas`: falso acoplamiento VB6↔SSIS en el linaje y en la propiedad de escritura | Nodos `table:stg.polizas` y `table:dbo.polizas`. Sin esquema se asume `dbo`, como hace SQL Server (configurable con `VB6GRAPH_DEFAULT_SCHEMA`); se descartan servidor y base; las temporales (`#x`) no llevan esquema |
| Rutas en Windows (`0002-rutas-windows.patch`) | `os.path.normpath` devuelve `\\` en Windows: los `.frm`/`.bas` de una subcarpeta no se asociaban a su `.vbp` y quedaban en `_orphans`, lo que además ocultaba código muerto | `posixpath.normpath`: los archivos quedan en su proyecto, igual que en Linux |
| Procedimientos almacenados | Nodo `table` con `object_type=procedure` y arista `READS` heurística | Nodo propio `db_proc:esquema.nombre`; desde VB6 la arista `EXECUTES_PROC`, desde SSIS `SSIS_EXECUTES_PROC` |

Archivos que toca: `model.py` (`qualify_db_object`, `table_id`, `db_proc_id`, nuevos `db_proc` y `EXECUTES_PROC`), `resolve.py` y `ssis.py` (creación de nodos), `report.py` (sección Tablas y `tablas.csv`), `mcp_server.py` (`who_touches_table` acepta tablas y procedimientos), `enrich/facts.py` y `cli.py` (`trace`). El formato de `tablas.csv` no cambia: la columna `table` trae `table:esquema.tabla` o `db_proc:esquema.nombre`.

Si se reindexa con un vb6graph sin el parche, `tools/vb6graph_puente/grafo.py` lo avisa.

Queda pendiente para el autor: la semántica de una tarea SSIS que falla con su rama de error (en ADF un try-catch deja el pipeline en *Succeeded*) no es parte del grafo. La fábrica la resuelve en `ssis2adf` agregando la actividad `Fail`.

# Plan POC — Ingeniería inversa y modernización (Pacífico Seguros)

## Contexto

| Componente actual | Tecnología | Destino propuesto |
|---|---|---|
| ETL | SSIS (paquetes `.dtsx`) | Azure Data Factory (pipelines + Data Flows) |
| Lógica de negocio en BD | T-SQL (SPs, funciones, vistas) | Azure SQL DB / Managed Instance (SPs migrados o la lógica sacada al servicio) |
| Aplicación | VB6 / .NET Framework | **Por definir** (lenguaje y contenedor Docker en la nube según las especificaciones del cliente) |

## Estado

La POC está implementada sobre un sistema legado **emulado** (`legacy/`), a la espera de los fuentes reales y de las especificaciones de destino:

- [x] Ingeniería inversa: inventario automático + REA sobre el componente compilado (`reingenieria/HALLAZGOS.md`)
- [x] SSIS → ADF con convertidor automático (`adf/`, `tools/ssis2adf`)
- [x] VB6 + COM → API .NET 10 LTS con pruebas de paridad contra el binario legado (`app/`)
- [x] El sistema nuevo invoca ADF por su API REST; en local, contra un emulador (`adf-emulador/`)
- [x] Entorno local con Docker Compose y demostración de punta a punta (`scripts/demo.sh`)
- [ ] Repetir con los fuentes/binarios reales del cliente
- [ ] Publicar el pipeline en una factoría real y desplegar la API según las especificaciones (contenedores, CI/CD)

## Fases

### Fase 0 — Recepción de insumos (pendiente del cliente)
- [ ] Fuentes SSIS (`.dtsx`, `.ispac`, `.conmgr`, `.params`, configuraciones de ambiente)
- [ ] Script de la BD (esquema + SPs + jobs del SQL Agent que ejecutan los paquetes)
- [ ] Fuentes VB6 (`.vbp`, `.frm`, `.bas`, `.cls`) o .NET (`.sln`, `.vbproj`/`.csproj`)
- [ ] Datos de muestra anonimizados (sin datos reales de asegurados)
- [ ] **Especificaciones de destino**: lenguaje, imagen base Docker, orquestador (AKS / Container Apps / App Service), CI/CD, estándares de seguridad

### Fase 1 — Ingeniería inversa (automatizada + revisión)

Se usan dos herramientas que se complementan:

| Artefacto | Herramienta | Qué entrega |
|---|---|---|
| Paquetes SSIS (`.dtsx`, XML) | `tools/re_inventario` | Conexiones, flujo de control, SQL de cada tarea, data flows |
| T-SQL (scripts de la BD) | `tools/re_inventario` | Objetos definidos, tablas leídas/escritas, EXEC |
| Fuentes VB6 / .NET | `tools/re_inventario` | Cadenas de conexión, SQL embebido, SPs llamados |
| **Assemblies .NET compilados** (`.dll`/`.exe` sin fuente) | **REA** (`rea-agents`) | Metadatos, tipos, métodos e instrucciones CIL; no requiere herramientas extra |
| **Ejecutables VB6 compilados** (sin fuente) | **REA** + Ghidra/IDA/Hopper | Pseudocódigo, strings (SQL y cadenas de conexión), símbolos, llamadas |
| Script Tasks de SSIS compilados | **REA** (.NET) | El código C#/VB embebido en el paquete |
| Front web (si existe) | **REA** (análisis de sitio) | Estructura, scripts y tráfico de red |

REA ([github.com/morluto/rea](https://github.com/morluto/rea), licencia MIT) es un servidor MCP que conecta al agente con herramientas de ingeniería inversa; el análisis corre en la máquina local. Se instala con `npx rea-agents setup` (Node.js ≥ 22.19). Para binarios nativos (VB6) necesita Ghidra (gratuito), IDA o Hopper. Los VB6 compilados en **P-Code** se descompilan peor que los compilados a código nativo: conviene preguntar al cliente cómo los compila, o pedir los fuentes.

Pasos:
1. Copiar los fuentes en `fuentes/` (está en `.gitignore` para no versionar código ni credenciales del cliente).
2. Ejecutar `python tools/re_inventario/inventario.py fuentes salida/cliente`.
3. Si falta algún fuente, analizar los binarios con REA: lo que encuentre (SQL, tablas, reglas) se agrega al inventario.
4. Con el inventario, documentar:
   - Linaje de datos: origen → transformación → destino por paquete.
   - Reglas de negocio de cada SP (en lenguaje natural, con su caso de prueba).
   - Funcionalidades de la app (pantallas → SPs/SQL → tablas).
   - Calendario de ejecución (jobs del SQL Agent) y dependencias entre paquetes.
5. Marcar los puntos de riesgo: Script Tasks (C#/VB embebido), componentes de terceros, rutas UNC/archivos locales, SQL dinámico, cursores, tablas temporales globales, `xp_cmdshell`, linked servers.

### Fase 2 — Diseño destino
- Tabla de equivalencias SSIS → ADF (ver `docs/MAPEO_SSIS_ADF.md`) aplicada a cada tarea.
- Decidir por cada SP: **mantener en Azure SQL** (lo más rápido para la POC) o **llevar a código** del nuevo servicio.
- Arquitectura de la app: API REST en contenedor + frontend (según especificación).

### Fase 3 — Construcción de la POC (un flujo de punta a punta)
- Elegir **un** paquete representativo y **una** funcionalidad de la app.
- Pipeline ADF como código (JSON/ARM/Bicep) en `adf/`.
- Servicio en Docker en `app/`.
- Infraestructura como código en `infra/`.

### Fase 4 — Validación
- Ejecutar el SSIS original y el pipeline ADF con los mismos datos de entrada; comparar los resultados tabla por tabla (conteos, checksums, diferencias por fila).
- Pruebas funcionales de la app migrada contra los mismos casos de la app legada.

## Estructura del repositorio

```
docs/                 Plan, mapeos y hallazgos
tools/re_inventario/  Inventario automático (SSIS, T-SQL, VB6/.NET)
samples/              Fuentes sintéticos para probar las herramientas
fuentes/              Fuentes reales del cliente (NO se versionan)
salida/               Reportes generados (NO se versionan)
adf/  app/  infra/    (se crean en la Fase 3)
```

## Preguntas abiertas para el cliente
1. ¿Cuántos paquetes SSIS y SPs son en total? ¿Hay paquetes que llaman a otros paquetes?
2. ¿La app es VB6, .NET Framework o ambas? ¿Versión de .NET? ¿Tienen los fuentes o solo los ejecutables? (VB6: ¿compilado a P-Code o a código nativo?)
3. ¿El SQL Server se queda on-premise (requiere Self-hosted Integration Runtime) o también migra a Azure?
4. ¿Los orígenes son archivos (FTP, carpetas compartidas), otras BD o APIs?
5. ¿Hay Script Tasks o componentes de terceros en los paquetes?
6. ¿Qué nube y qué servicio de contenedores usan? ¿Tienen estándar de CI/CD (Azure DevOps / GitHub Actions)?

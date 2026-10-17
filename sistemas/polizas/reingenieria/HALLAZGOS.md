# Hallazgos de la ingeniería inversa

Sistema legado emulado en `sistemas/polizas/fuentes/` (rutas de esta página relativas a `sistemas/polizas/`):

| Pieza | Artefacto | Cómo se analizó |
|---|---|---|
| ETL | `ssis/CargaPolizas.dtsx` | `tools/re_inventario` → `inventario/inventario.md` |
| Lógica en BD | `db/*.sql` (2 SPs) | `tools/re_inventario` |
| Aplicación | `vb6/` (formulario, módulo, proyecto) | `tools/re_inventario` |
| Componente de tarificación | `componente-net/bin/Pacifico.Tarificador.dll` (**solo binario**) | **REA** + ILSpy (`rea/`) |

## 1. Componente `Pacifico.Tarificador.dll` (con REA)

### Identificación (`rea inspect-managed-artifact` → `rea/Pacifico.Tarificador.dll/artifact.json`)
- Assembly .NET Framework (metadatos v4.0.30319), solo IL, AnyCPU, versión 2.3.1.
- SHA-256 `55030199ef3febbdb750ed2f0105f4fe4093e379bf5d1c191be2633451b6343a`.
- Clase `Pacifico.Tarificador.Tarificador` con `[ComVisible]` y ProgId `PacificoTarificador.Tarificador`: es el objeto que la app VB6 crea con `CreateObject`.

### Miembros y evidencia (`rea inspect-managed-members` → `rea/Pacifico.Tarificador.dll/members.json`)
- Métodos públicos: `CalcularPrima(string, int, decimal, int) : decimal`, `ObtenerTasa(string) : decimal`, `FactorEdad(string, int) : decimal`.
- Constantes con nombre: `PRIMA_MINIMA`, `DESCUENTO_SIN_SINIESTROS`, `RECARGO_POR_SINIESTRO` (decimal) y `MAX_SINIESTROS_RECARGO` (int).
- Textos literales: `AUTO`, `HOGAR`, `VIDA`, `Tipo de seguro no soportado: `, `El asegurado debe ser mayor de edad`, `La suma asegurada debe ser positiva`.
- Llamadas relevantes: `Math.Min(int, int)`, **`Math.Round(decimal, int)`**, y `Strings.UCase`/`Strings.Trim`/`Operators.CompareString` del runtime de Visual Basic.

### Reconstrucción (`ilspycmd` 11.1 → `rea/Pacifico.Tarificador.dll/decompilado/`; `rea import-managed-reconstruction` → `rea/Pacifico.Tarificador.dll/reconstruccion_*.verificada.json`)
REA ancló los 3 métodos al SHA-256 y MVID del binario, al hash de cada firma y a la forma del IL. REA marca el código decompilado como **inferencia**; por eso las reglas se validan además con pruebas de paridad que ejecutan el binario legado (`app/tests/Pacifico.Polizas.Pruebas/ParidadLegadoTests.cs`).

### Reglas de negocio recuperadas

| Regla | Valor |
|---|---|
| Tasa por tipo | AUTO 4,5 % · HOGAR 0,35 % · VIDA 0,6 % de la suma asegurada; otro tipo → error |
| Factor edad | < 18 → error · 18–24 → 1,30 · 25–60 → 1,00 · > 60 → 1,80 (VIDA) / 1,45 (otros) |
| Siniestralidad | 0 siniestros → −5 % · 1 o más → +15 % por siniestro, con un máximo de 3 (+45 %) |
| Prima mínima | 12,5 UF (se aplica **después** del ajuste por siniestros) |
| Redondeo | 2 decimales con `Math.Round(decimal, int)` = **redondeo bancario** (al par) |
| Comparación de tipo | `UCase(Trim(x))`: no distingue mayúsculas ni espacios |

## 2. Problemas detectados (la "problemática" que se emula)

| # | Problema | Dónde | Impacto | Tratamiento en la POC |
|---|---|---|---|---|
| P1 | **Redondeo distinto en dos lugares**: el componente redondea al par (`Math.Round`) y `usp_RecalcularPrimas` usa `ROUND` de T-SQL (aleja de cero). Ej.: AUTO, 22 años, 600 UF, sin siniestros = 33,345 → cotiza **33,34**, la BD guarda **33,35** | DLL + SP | Diferencias de centavos entre cotización y cobro | Se preserva el comportamiento del componente (`MidpointRounding.ToEven` explícito) y queda cubierto por una prueba de paridad; la unificación es una decisión de negocio |
| P2 | Regla de siniestralidad **duplicada** en el componente y en `usp_RecalcularPrimas` | DLL + SP | Cambiar una regla obliga a tocar dos sistemas | En .NET 10 la regla queda en un solo lugar (`Tarificador`); el SP se mantiene por ahora |
| P3 | **SQL armado concatenando texto** (`"WHERE IdCliente = " & txtCliente.Text`) | `frmPolizas.frm` | Inyección SQL | Consultas parametrizadas en la API |
| P4 | Carga lanzada con `Shell dtexec` **sin esperar ni ver el resultado** ("revise el log del servidor") | `frmPolizas.frm` | El usuario no sabe si la carga falló | La API dispara el pipeline de ADF y expone su estado y el de cada actividad |
| P5 | Credenciales en texto plano en el código y en el paquete | `modConexion.bas`, `.dtsx` | Seguridad | Linked services de ADF con Azure Key Vault; la API recibe la conexión por configuración |
| P6 | El Lookup `Buscar Cliente` falla toda la carga ante un RUT desconocido (NoMatchBehavior = 0) | `.dtsx` | La carga se cae completa | Se traslada como validación explícita en `usp_ConsolidarPolizas` con mensaje claro |
| P7 | En ADF, un manejador "Upon Failure" que termina bien **deja el pipeline en Succeeded** (patrón try-catch), a diferencia de SSIS, donde el paquete falla | Migración SSIS → ADF | Una carga fallida se vería como exitosa | El convertidor agrega una actividad `Fail` al final de la rama de error |
| P9 | **Edad mal calculada**: `CalcularEdad` usa `DateDiff("yyyy", ...)`, que cuenta cambios de año calendario. Ej.: nacido el 20-12-2001, al 17-10-2026 tiene 24 años pero VB6 calcula 25 y pasa del factor 1,30 al 1,00 | `modConexion.bas` | Antes del cumpleaños, cotiza más barato a quien tiene 24 años (factor 1,00 en vez de 1,30) y más caro a quien tiene 60 (1,45 en vez de 1,00) | Configurable: `Cotizacion:CalculoEdad` = `Vb6DateDiff` (igual al legado, por defecto) o `Exacta` (corregido) |
| P8 | Dependencia de COM + .NET Framework 4.8 + VB6 (solo Windows) | Arquitectura | No se puede contenerizar en Linux | Todo pasa a .NET 10 en contenedores Linux |

## 3. Cómo reproducir

```bash
npm install -g rea-agents
# Inventario + REA (con decompilación ILSpy e import de la reconstrucción) + SSIS → ADF
python3 tools/portafolio/portafolio.py analizar --solo polizas --decompilar
```

Por dentro, para cada binario .NET se ejecuta `rea inspect-managed-artifact`, `rea inspect-managed-members`, `rea inspect-managed-native-boundaries`, la decompilación con `ilspycmd -p` y `rea import-managed-reconstruction` por tipo (`tools/rea/analizar_binarios.py`).

Con los ejecutables VB6 reales del cliente (código nativo o P-Code) el análisis requiere un motor nativo para REA (Ghidra, IDA o Hopper) con `rea inspect` / `rea decompile`; mientras tanto la herramienta extrae del ejecutable los textos (SQL, cadenas de conexión, ProgIds COM).

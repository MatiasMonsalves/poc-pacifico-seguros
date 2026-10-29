# Demo de la POC en Windows, paso a paso

Para presentar en un equipo con Windows 10/11, Docker Desktop y Python, todo desde PowerShell y sin Ubuntu. La demo recorre el sistema de ejemplo *pólizas* (VB6 + componente COM .NET 4.8 + SSIS + SQL Server) en 5 pasos, y en cada paso se detiene hasta que usted presione Enter.

## A. La víspera (una sola vez, 20–30 minutos)

1. **Abra Docker Desktop** y espere a que abajo a la izquierda diga *Engine running*. En *Settings → Resources* deje al menos 4 GB de memoria (SQL Server los necesita).
2. **Abra PowerShell** (no hace falta como administrador) y vaya al repositorio:
   ```powershell
   cd $HOME\poc-pacifico-seguros
   ```
3. **Traiga la última versión.** Las ejecuciones anteriores regeneran archivos del repositorio; `git restore .` descarta esos cambios locales para que `git pull` no se queje:
   ```powershell
   git restore .
   git pull origin poc/estructura-ingenieria-inversa
   ```
4. **Revise el equipo.** Debe terminar en *Todo listo*. Si algo falta, el script dice cómo corregirlo:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\windows\requisitos.ps1
   ```
5. **Prepare la demo.** Descarga las imágenes (SQL Server, SDK de .NET 10), construye y levanta el entorno, y hace un ensayo completo de corrido:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\windows\presentacion.ps1 -Preparar
   ```
   Debe terminar con *Listo para presentar*. La primera vez tarda porque descarga cerca de 3 GB; después todo queda en caché.
6. Opcional, para tener el respaldo completo (análisis, 53 pruebas .NET, 20 de punta a punta, cobertura y plan):
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\windows\verificar.ps1
   ```

Con proxy corporativo, antes de los pasos 4 a 6: `$env:CA_BUNDLE = 'C:\ruta\certificado.pem'`. Si un puerto está ocupado (1433, 8080, 8081, 5080): `copy .env.example .env` y cambie el puerto.

## B. Antes de entrar a la reunión (2 minutos)

1. Docker Desktop abierto, con *Engine running*.
2. Abra **Windows Terminal** con PowerShell, maximizado, con letra grande (Ctrl + `+`), y vaya al repositorio con `cd $HOME\poc-pacifico-seguros`.
3. Tenga a mano el navegador y la lámina.

## C. La demo (10–15 minutos)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\presentacion.ps1 -AbrirNavegador
```

Presione **Enter** para pasar de un paso al siguiente. Qué mostrar y qué decir en cada uno:

| Paso | Qué se ve en pantalla | Qué decir |
|---|---|---|
| **1. Assessment** | Inventario del VB6 y del SSIS, riesgos (componente COM), 2 rutinas de código muerto y la tabla de quién lee y escribe cada tabla, con archivo y línea | "Antes de tocar nada, la herramienta de Fabián (vb6graph) arma un mapa del sistema. Cada hallazgo apunta a la línea exacta del código original. Se migra solo lo que se usa: 2 rutinas muertas quedan fuera." |
| **2. VB6 → .NET 10** | La tabla de qué se convirtió y adónde; el código VB6 original (SQL armado con texto del usuario) junto al C# generado (consulta parametrizada); la compilación sin errores | "El convertidor genera una API moderna desde el VB6. El código nuevo dice de qué línea del VB6 viene. De paso se cierra un riesgo de seguridad: el VB6 era vulnerable a inyección SQL." |
| **3. SSIS → ADF** | El paquete convertido en un pipeline de Azure Data Factory, actividad por actividad, validado y sin contraseñas (van a Key Vault) | "El proceso nocturno pasa a la nube de Azure. Se respeta su comportamiento ante errores: si falla, se registra y el proceso queda marcado como fallido, igual que antes." |
| **4. Ejecución** | La app generada responde y rechaza la inyección; la app terminada cotiza 33,34 UF, igual que el sistema antiguo; dos cargas de ADF, una exitosa y otra fallida, con el detalle de cada actividad | "Esto ya corre. El resultado es idéntico al sistema antiguo, al centavo. Y ahora se ve qué pasó en cada carga, cosa que antes no se veía." |
| **5. Plan** | La matriz de trazabilidad: cada pieza del sistema antiguo, qué se decidió, dónde quedó, con qué pruebas y en qué estado; % de avance | "Así se gestiona la migración: cada pieza tiene dueño, prueba y estado. El mismo proceso se repite para cada sistema del portafolio." |

Al terminar se abren en el navegador:
- **http://localhost:8080**: la pantalla nueva. Busque el cliente 1, cotice el cliente 5 (AUTO, 600 UF, 0 siniestros) y cargue `polizas_20261017.csv` y `polizas_rut_invalido.csv`.
- **El reporte de vb6graph** (`sistemas\polizas\reingenieria\vb6graph\reporte.html`): inventario, tablas, riesgos y código muerto, para quien quiera ver el detalle.

Para seguir explicando: `sistemas\polizas\transformacion\Polizas.Generado\Endpoints.cs` (código generado con el VB6 original en comentarios), `sistemas\polizas\adf\pipeline\PL_CargaPolizas.json` (el pipeline) y `sistemas\polizas\plan\AVANCE.md`.

## D. Si algo falla durante la presentación

| Síntoma | Qué hacer |
|---|---|
| "Docker Desktop no está corriendo" | Ábralo, espere a *Engine running* y repita el comando |
| El paso 4 tarda o no levanta | Siga sin contenedores: `scripts\windows\presentacion.ps1 -SinDocker` muestra los pasos 1, 2, 3 y 5 (sin compilar ni ejecutar) |
| `port is already allocated` | Otro programa usa el puerto: `copy .env.example .env`, cambie el puerto y repita |
| Quiere mostrarlo sin pausas | Agregue `-SinPausa` |

## E. Al terminar

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\presentacion.ps1 -Apagar
```

Apaga los contenedores. Las imágenes quedan en caché para la próxima vez.

## F. Armar el grafo con otros fuentes (instalar vb6graph)

Sin vb6graph, la demo muestra el grafo guardado en el repositorio ("vb6graph no está instalado en este equipo"). Para que el grafo se arme en vivo desde los fuentes que usted le pase, instálelo una vez:

1. **Instale uv** (instala vb6graph y descarga Python 3.12 si hace falta). Luego cierre y vuelva a abrir PowerShell:
   ```powershell
   winget install astral-sh.uv
   ```
2. **Descomprima el paquete de Fabián** (`vb6graph-portable-0.1.0.zip`), por ejemplo en Descargas:
   ```powershell
   Expand-Archive "$HOME\Downloads\vb6graph-portable-0.1.0.zip" "$HOME\Downloads\vb6graph"
   cd "$HOME\Downloads\vb6graph\vb6graph-portable-0.1.0"
   ```
3. **Instálelo** y deje el comando `vb6graph` en el PATH. Luego cierre y vuelva a abrir PowerShell:
   ```powershell
   uv tool install --python 3.12 --with openpyxl .\vb6graph-0.1.0-py3-none-any.whl
   uv tool update-shell
   ```
4. **Configúrelo y revíselo.** Sin compilador C usa el parser de respaldo y funciona igual. `doctor` debe terminar en *estado: OK*:
   ```powershell
   vb6graph setup
   vb6graph doctor
   ```
5. **Aplique el parche de esquemas y procedimientos**, desde la carpeta de la demo:
   ```powershell
   cd "C:\Users\MatiasMonsalve\Desktop\inAdvance\Pacifico Seguros\poc-demo"
   python tools\vb6graph_puente\aplicar_parche.py
   ```

Desde ahí:

- **La demo normal** arma en vivo el grafo de pólizas: el paso 1 dice *vb6graph indexó los fuentes*.
- **Otros fuentes** (una carpeta con `.vbp`, `.frm`, `.bas`, `.cls` y, si hay, `.dtsx`): se arma su grafo, se muestra el assessment (inventario, riesgos, código muerto, quién lee y escribe cada tabla) y se abre el reporte HTML:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\windows\presentacion.ps1 -Fuentes "C:\ruta\a\los\fuentes"
  ```
  El grafo y el reporte quedan en `portafolio\vb6graph\<carpeta>\`, que no se sube a GitHub porque incluye el texto de los fuentes.
- **El proceso completo** con esos fuentes (conversión a .NET 10, ADF, plan): cópielos en `sistemas\<id>\fuentes\` (`vb6\`, `ssis\`, `db\`) y siga [GUIA_MULTISISTEMA.md](GUIA_MULTISISTEMA.md).

Según la documentación de vb6graph, su instalación en Windows no se ha probado: si algún paso falla, mándele la captura a Fabián.

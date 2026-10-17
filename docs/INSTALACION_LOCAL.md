# Levantarlo en su equipo y probar el proceso completo

Todo corre en contenedores: **no necesita instalar .NET, SQL Server ni Visual Studio**. Necesita Docker, Python 3.9+, Git y, opcionalmente, Node.js para REA.

La primera vez se descargan unos **4,5 GB** de imágenes (SQL Server 2,4 GB, SDK de .NET 10 1,3 GB y otras) y la verificación completa tarda unos 10 minutos. Las siguientes ejecuciones tardan alrededor de 1,5 minutos. Reserve **10 GB libres** en disco y **4 GB de RAM** para Docker (8 GB recomendado).

## 1. Instalar los requisitos

### Windows 10 y 11

**Requisitos del equipo**

| Requisito | Detalle |
|---|---|
| Windows | 64 bits. Windows 10 **22H2** (build 19045) recomendado; WSL2 funciona desde la versión 2004 (build 19041) |
| Edición | Cualquiera con la opción recomendada. Docker Desktop **no** soporta la edición Home |
| Virtualización | Activada en la BIOS/UEFI (Intel VT-x o AMD-V). Se ve en *Administrador de tareas → Rendimiento → CPU → Virtualización: Habilitado* |
| Memoria | 8 GB mínimo, 16 GB recomendado |
| Disco | 15 GB libres en C: |
| Permisos | Administrador local para instalar WSL (una sola vez); si no lo tiene, lo hace TI |
| Red | Acceso a `mcr.microsoft.com`, `download.docker.com`, `api.nuget.org` y GitHub; con proxy corporativo, el certificado raíz de la empresa |

**Paso 0: revisar el equipo.** Descargue `scripts/windows/revisar-windows.ps1` desde GitHub (botón *Download raw file*) y ejecútelo en PowerShell. No instala nada:

```powershell
powershell -ExecutionPolicy Bypass -File .\revisar-windows.ps1
```

**Opción recomendada: Docker Engine dentro de WSL2 (sin Docker Desktop).** Es gratuita y no depende de la edición ni del ciclo de soporte de Windows.

1. PowerShell **como administrador**: `wsl --install -d Ubuntu-24.04` (si WSL ya existe: `wsl --update`). Reinicie el equipo y cree el usuario de Ubuntu cuando se lo pida.
2. En la terminal de **Ubuntu**:
   ```bash
   git clone https://github.com/matiasmonsalves/poc-pacifico-seguros.git
   cd poc-pacifico-seguros
   git checkout poc/estructura-ingenieria-inversa
   scripts/instalar-wsl.sh
   ```
   Instala Docker Engine y Compose, Python, Git y, si puede, Node.js 22 con REA (opcional). También activa systemd para que Docker arranque solo.
3. En PowerShell: `wsl --shutdown`. Vuelva a abrir Ubuntu y siga en el [paso 2](#2-obtener-el-código-y-revisar-el-equipo) (`scripts/requisitos.sh`).

Las páginas (`http://localhost:8080`, etc.) se abren desde el navegador de Windows: WSL2 publica los puertos en `localhost`.

**Alternativa: Docker Desktop.** Úsela solo si cumple tres condiciones: Windows 10 22H2 **Pro, Enterprise o Education**, soporte vigente de Microsoft (por ejemplo, con actualizaciones extendidas ESU) y **licencia de Docker** cuando la empresa tiene más de 250 empleados o más de USD 10 millones de ingresos anuales.
- Instálelo con el backend WSL 2.
- Active *Settings → Resources → WSL integration → Ubuntu-24.04*.
- No ejecute `instalar-wsl.sh`. Instale solo `sudo apt install -y git python3 curl` en Ubuntu.

**Si WSL tiene poca memoria**, cree `C:\Users\<usuario>\.wslconfig` con estas líneas y ejecute `wsl --shutdown`:

```ini
[wsl2]
memory=8GB
```

> Clone el repositorio dentro de Ubuntu (`~/...`), **no** en `/mnt/c/...`: en el disco de Windows es mucho más lento y pueden fallar los permisos de los scripts.

### macOS

1. Instalar **Docker Desktop**. En Mac con Apple Silicon (M1–M4): *Settings → General* → **Use Rosetta for x86_64/amd64 emulation**, porque la imagen de SQL Server es solo amd64.
2. *Settings → Resources*: al menos 4 GB de memoria.
3. `brew install git python node && npm install -g rea-agents` (REA es opcional).

### Linux

Docker Engine con el plugin de Compose (`docker compose version`), el usuario en el grupo `docker`, más `git python3 curl`. Opcional: Node.js 22 y `npm install -g rea-agents`.

### Detrás del proxy de la empresa

Si la red inspecciona HTTPS, las descargas de imágenes y de paquetes NuGet fallan con errores de certificado.
- Pida a TI el **certificado raíz** de la empresa (`.crt` o `.pem`).
- Configure el proxy en Docker Desktop (*Settings → Resources → Proxies*).
- Ejecute los scripts con `CA_BUNDLE=/ruta/certificado.pem`. `scripts/requisitos.sh` detecta este caso y lo indica.

## 2. Obtener el código y revisar el equipo

```bash
git clone https://github.com/matiasmonsalves/poc-pacifico-seguros.git
cd poc-pacifico-seguros
git checkout poc/estructura-ingenieria-inversa
scripts/requisitos.sh
```

`requisitos.sh` revisa Python, Docker y Compose, la memoria, la arquitectura del equipo, los puertos, el acceso a los registros (detecta el proxy), los saltos de línea de los scripts y REA. Indica cómo corregir cada problema.

**Si un puerto está ocupado** (por ejemplo, ya tiene SQL Server en el 1433):
```bash
cp .env.example .env     # y cambie SQL_PORT, API_PORT, GEN_PORT o ADF_PORT
```

## 3. Probar el proceso completo

```bash
scripts/verificar.sh                       # con proxy: CA_BUNDLE=/ruta/cert.pem scripts/verificar.sh
```

Ejecuta los 7 pasos y deja el informe en `portafolio/VERIFICACION.md`:

1. **Análisis** de los dos sistemas de ejemplo: inventario, REA sobre los binarios y conversión SSIS → ADF.
2. **Transformación VB6 → .NET 10** con `vb62net`, y compilación del resultado.
3. **Validación** de los pipelines de ADF.
4. **Pruebas .NET** (53), incluida la paridad contra el binario legado.
5. **Entorno local:** SQL Server con las BDs legadas, emulador de ADF, app terminada y app generada.
6. **19 verificaciones de punta a punta.**
7. **Cobertura:** cada evento VB6 tiene su reemplazo en la app nueva.

Debe terminar con `Todo verificado`. Si un paso falla, el informe indica su log en `portafolio/logs/`.

## 4. Verlo funcionando

El entorno queda levantado al terminar `verificar.sh`. También puede levantarlo con `docker compose up -d --build`.

| Qué | Dónde |
|---|---|
| Pantalla de pólizas (reemplaza al formulario VB6) | http://localhost:8080 |
| App generada automáticamente desde el VB6 | http://localhost:8081/api/polizas/buscar?Cliente=1 |
| API del emulador de ADF | http://localhost:5080/subscriptions/x/resourceGroups/x/providers/Microsoft.DataFactory/factories/polizas/pipelines |
| SQL Server (SSMS, Azure Data Studio o VS Code) | `localhost,1433` · usuario `sa` · clave `Poc_Pacifico_2026!` · BDs `Seguros`, `Siniestros`, `CoreLegado` |

Recorrido sugerido en http://localhost:8080:

1. **Buscar** el cliente 1.
2. **Cotizar** el cliente 5 (AUTO, 600 UF, 0 siniestros): da **33,34 UF**, igual que el componente legado.
3. **Cargar** `polizas_20261017.csv`: el pipeline termina en *Succeeded*. Luego busque el cliente 4 o 5 para ver las pólizas nuevas.
4. **Cargar** `polizas_rut_invalido.csv` y `polizas_formato_invalido.csv`: los pipelines terminan en *Failed* y se ve en qué actividad falló cada uno y por qué.
5. En SQL Server, consulte `log.ErroresETL` en la BD `Seguros`: ahí queda registrada la falla, igual que hacía el paquete SSIS.

Para ver lo que se transformó:
- `sistemas/polizas/transformacion/MAPEO_VB6_NET.md` y `Polizas.Generado/Endpoints.cs`: el VB6 convertido a .NET, con el código original en comentarios.
- `sistemas/*/adf/`: los pipelines generados desde los `.dtsx`.
- `portafolio/PORTAFOLIO.md` y `sistemas/*/reingenieria/RESUMEN.md`: el análisis de cada sistema.

## 5. Con un sistema real

```bash
python3 tools/portafolio/portafolio.py nuevo cobranza --nombre "Cobranza"
# Copiar los fuentes en sistemas/cobranza/fuentes/ (db/, ssis/, vb6/, dotnet/, bin/)
scripts/verificar.sh --sin-docker
```

Revise `sistemas/cobranza/reingenieria/RESUMEN.md`, `sistemas/cobranza/transformacion/MAPEO_VB6_NET.md` y `sistemas/cobranza/adf/REPORTE_CONVERSION.md`. Los fuentes reales no se suben a git (`.gitignore`). Para ejecutarlo también en el entorno local, siga [GUIA_MULTISISTEMA.md](GUIA_MULTISISTEMA.md).

## Apagar y empezar de cero

```bash
docker compose down          # detiene todo; al volver a levantarlo las BDs se crean de nuevo con los datos de ejemplo
```

## Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `\r: command not found` o `bad interpreter` | Scripts con saltos de línea de Windows: clone de nuevo (el repositorio trae `.gitattributes`) o `git add --renormalize . && git checkout -- .` |
| `port is already allocated` | Puerto ocupado: `cp .env.example .env` y cambie el puerto |
| `certificate verify failed`, `UntrustedRoot` o `NU1301` | Proxy corporativo: `CA_BUNDLE=/ruta/cert.pem` (ver arriba) |
| `sqlserver` se reinicia o queda *unhealthy* | Poca memoria para Docker (mínimo 4 GB), o falta Rosetta en Apple Silicon |
| `db-init` termina con error | `docker compose logs db-init`: normalmente SQL Server todavía no estaba listo o la clave no cumple la política (mínimo 8 caracteres con mayúsculas, minúsculas, números y símbolos) |
| La primera ejecución es lenta | Descarga de imágenes y paquetes NuGet; las siguientes reutilizan la caché |
| REA no instalado | Es opcional: se reutiliza el análisis de binarios guardado en el repositorio |
| `WslRegisterDistribution failed with error: 0x80370102` | La virtualización está desactivada en la BIOS/UEFI, o falta la característica *Plataforma de máquina virtual* (la activa `wsl --install`) |
| `wsl --install` muestra la ayuda en vez de instalar | Windows 10 anterior a 2004 o sin actualizar: actualice a 22H2 con Windows Update |
| `permission denied ... docker.sock` en Ubuntu | Después de `instalar-wsl.sh` falta reiniciar WSL: `wsl --shutdown` en PowerShell y abrir Ubuntu de nuevo |
| `Cannot connect to the Docker daemon` en Ubuntu | Docker no arrancó: `sudo systemctl start docker`; si systemd no está activo, `sudo service docker start` |

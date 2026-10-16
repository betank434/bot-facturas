# Facturador Saint Enterprise - Guía de Arquitectura y Reglas del Proyecto

Este documento contiene las reglas, arquitectura y procedimientos estándar para el desarrollo, compilación y despliegue de **Facturador Saint**.
Cualquier agente que trabaje en este repositorio en cualquier PC debe seguir estrictamente estas directrices.

---

## 1. Repositorio Oficial y Control de Versiones

- **Repositorio Remoto**: `https://github.com/betank434/bot-facturas.git`
- **Owner**: `betank434`
- **Repo**: `bot-facturas`
- **Rama principal**: `main`
- **Herramienta recomendada**: GitHub Desktop o Git CLI.
- **Ruta de Git en GitHub Desktop**: `C:\Users\<Usuario>\AppData\Local\GitHubDesktop\app-*\resources\app\git\cmd\git.exe`
- **Protocolo de subida (Push)**: Para evitar que comandos de terminal se queden colgados esperando autenticación gráfica de Windows (`git-credential-manager`), el asistente realiza commits locales y el usuario pulsa **Push origin** en GitHub Desktop (1 clic).

---

## 2. Dependencias del Entorno y Preparación de Nuevas PCs

- **Script Automatizado de Instalación**:
  Ejecutar con doble clic: `INSTALADOR_DEPENDENCIAS_PC.bat`
  - Detecta e instala Python 3.12 (evitando venvs de terceros como `hermes-agent`).
  - Restaura automáticamente `pip` si está ausente mediante `ensurepip` o `get-pip.py`.
  - Instala todas las dependencias desde `requirements.txt`:
    - `pymupdf>=1.23.0` (lectura y extracción de facturas PDF)
    - `pyperclip>=1.8.2` (comunicación con portapapeles)
    - `pillow>=10.0.0` (procesamiento de imágenes de artículos)
    - `openpyxl>=3.1.2` (soporte y auditoría Excel)
    - `pynput>=1.7.6` (control y atajos F8, F7, F12)
    - `winocr>=0.0.14` (OCR nativo de Windows 10/11 sin dependencias externas)
    - `pyinstaller>=6.0.0` (compilación a ejecutable nativo de Windows)
  - Detecta e instala Inno Setup 6 (winget: `JRSoftware.InnoSetup` o descarga directa oficial de GitHub).

---

## 3. Reglas Críticas del Sistema (No Romper)

### A. Persistencia y Permisos en Windows (Smart Storage)
- La aplicación se instala frecuentemente en `C:\Program Files\Facturador Saint`.
- Por políticas de seguridad de Windows, usuarios estándar **NO tienen permiso de escritura** en `C:\Program Files`.
- Por tanto, la función `_resolve_storage_file(filename)` en `facturador_saint.py`:
  1. Comprueba si el archivo ya existe en `%LOCALAPPDATA%\FacturadorSaint\`. Si existe, lo usa con máxima prioridad.
  2. Si no, comprueba si `base_dir` es escribible. Si lo es, usa `base_dir`.
  3. Si `base_dir` está protegido (solo lectura), copia los archivos base a `%LOCALAPPDATA%\FacturadorSaint\` y opera allí con **100% permisos garantizados para cualquier usuario**.
- `_save_user_config()` y `_save_replacement_rules()` atrapan `PermissionError` y redirigen automáticamente a `%LOCALAPPDATA%\FacturadorSaint\`.

### B. Fusión Inteligente de Configuraciones (Smart Merge)
- **Nunca sobrescribir los ajustes del cliente en una actualización**:
  - `_load_saved_config()`: Preserva todas las opciones ya guardadas por el usuario (ej: si desactivó OCR, se mantiene desactivado). Si en una nueva versión se introduce una nueva clave, se agrega con su valor por defecto sin alterar nada de lo que el cliente ya haya configurado.
  - `_load_replacement_rules()`: Conserva intactos todos los códigos y sus estados (`activo: True/False`). Solo agrega un nuevo código por defecto si su `codigo_origen` no existe en la lista del cliente.

### C. Conexión SSL y Sistema de Actualizaciones (Finales vs Beta)
- `updater.py` utiliza `_get_ssl_context()` con `ctx.check_hostname = False` y `ctx.verify_mode = ssl.CERT_NONE`.
- Esto previene el error crítico `[SSL: CERTIFICATE_VERIFY_FAILED]` en Windows 10 y en ejecutables compilados con PyInstaller.
- El repositorio oficial de releases es `betank434/bot-facturas`.
- **Regla Estricta de Versiones Beta**:
  - Al iniciar el programa, la comprobación automática en segundo plano (`_auto_check_updates`) **NUNCA** debe notificar ni abrir ventanas emergentes si se publica una versión Beta (`prerelease == True` o etiqueta con "beta"). Solo comprueba y notifica versiones finales/estables.
  - La descarga de versiones Beta se realiza **exclusivamente** cuando el usuario pulsa deliberadamente el botón `🧪 Descargar Beta` en la cabecera. Dicho botón consulta la lista de releases en GitHub, busca versiones beta con instalador `.exe`, y abre la ventana modal con estilo ámbar (`🧪`).

### D. Reglas de Inno Setup (`instalador.iss`)
- **Version Number**: `#define MyAppVersion "X.XX"` debe coincidir exactamente con `CURRENT_VERSION` en `updater.py`.
- **Exclusiones**: `[Files]` debe excluir `config_facturador.json` y `codigos_reemplazo.json` del empaquetado masivo recursivo, e instalarlos por separado con `Flags: onlyifdoesntexist; Permissions: users-full`.
- **Permisos**:
  - `[Dirs]` debe incluir `Name: "{app}"; Permissions: users-full`.
  - `[Run]` ejecuta `icacls.exe "{app}" /grant *S-1-5-32-545:(OI)(CI)F /T /C /Q` en modo oculto (`runhidden`) para garantizar permisos de control total a todos los usuarios de Windows sin importar el idioma del sistema.
- **Acceso Directo**: Solo se crean accesos directos para la aplicación y la carpeta de PDFs. **NO crear acceso directo para `facturas_json` en el escritorio**. En `[InstallDelete]` se elimina cualquier acceso anterior a esa carpeta.

### E. Interfaz de Usuario y Ciclo de Vida de Ventanas (Ventana de Auditoría OCR)
- **Regla Crítica**: Al cerrar la ventana de Auditoría OCR (`w` Toplevel), **NUNCA cerrar la aplicación ni transferir el foco a Saint Enterprise de forma obligatoria**, lo que causaría que Facturador Saint se oculte o desaparezca detrás de Saint.
- Tanto el cierre por la "X" (`WM_DELETE_WINDOW`) como el botón `✔️ Cerrar Auditoría` deben ejecutar `close_audit_only()`:
  1. Destruir únicamente el diálogo de auditoría (`w.destroy()`).
  2. Restaurar y traer al frente la ventana principal mediante `forzar_ventana_al_frente(self.root)`.
  3. Mantener el programa Facturador Saint 100% visible, enfocado y operativo en primer plano.
- La transferencia de foco hacia Saint solo se realiza si el usuario pulsa deliberadamente el botón `🖥️ Ir a Saint`.

### F. Motor de Auditoría OCR en Cuadrícula Saint Enterprise
- **Delimitación Estricta de Columnas**:
  - Columna **CANTIDAD**: abarca de `0.58` a `0.78` del ancho de pantalla/cuadrícula (abarca cantidades alineadas a la derecha).
  - Columna **PRECIO**: abarca de `0.79` a `0.915` del ancho.
  - Prohibido solapar estas columnas para evitar que cantidades (ej. 9, 17, 29, 32) sean leídas dentro de la celda de precio unitario.
- **Filtro de Descarte por Cantidad**: Cualquier candidato numérico dentro de la celda de precio que coincida con `found_qty` de la fila o con la cantidad esperada del producto es descartado. Si en la validación el precio tomado coincide con la cantidad y difiere del esperado, se busca automáticamente entre los candidatos secundarios y en los tokens `row_words` de la columna de precio.
- **Precios USD vs Bolívares (Bs)**: En Saint Enterprise, el precio en USD se muestra arriba en negrita y el precio en Bs abajo. En modo USD se omiten candidatos en la mitad inferior de la celda (`yc >= cell_h * 0.46`), candidatos con texto "Bs" y valores superiores a 500.
- **Captura de Última Fila**: `grid_bottom` se expande hasta `h - 32px` (hasta 91% del alto de la ventana) para asegurar que el último renglón visible nunca quede cortado ni se catalogue falsamente como faltante.
- **Prevención de Falsos Positivos**: Filas con totales ("TOTAL", "SUBTOTAL", "IVA", "BASE") y claves sintéticas `_row_` se excluyen de la lista de productos ajenos.

### G. Formatos de Documentos Soportados (`extractor.py`)
El motor de extracción detecta y procesa automáticamente los siguientes formatos (sin romper ninguno al agregar nuevos):
1. **Sigo, S.A. - Facturas de Consignación (`FTC-...`) y Órdenes de Compra (`ODC-...`)**: Extracción de precios en Bs. y USD, tasa de cambio y normalización de códigos a 8 y 12 dígitos.
2. **Grupo Abreu / Hiper Ahorro Aikoz / Mas X Menos (`Nro OCIS...` - Inversiones Barcelona Oriente 20.22 / 20.23, C.A)**:
   - Función `extraer_orden_compra_grupo_abreu(doc, ruta_pdf)`.
   - Extrae `Nro OCIS...`, `RIF`, `Sucursal` (almacén), `Razon Social` (cliente), `Fecha Emisión` y `Moneda` (`$ - Dolar`).
   - Limpia el sufijo `UND EMP` (`UNIDAD` / `NA`) de la descripción, normaliza códigos de 11 dígitos a 12 dígitos (UPC-A con 0 inicial) y valida `ITEM`, `SubTotal` y `Total` en USD.
3. **Norkut Cloud (`Documento: #ODC...` / Sigo Boca del Río)**: Función `extraer_orden_compra_norkut(doc, ruta_pdf)`, calcula tasa de cambio implícita desde el resumen `VES / USD`.
4. **Guuao (`Orden de compra #P...`)**: Función `extraer_orden_compra_guuao(doc, ruta_pdf)` para órdenes expresadas únicamente en Bolívares (`moneda: "VES"`).
5. **Presupuestos y Catálogos en Excel (`.xlsx` / `.xls`)**: Función `extraer_presupuesto_excel(ruta_excel)`.

---

## 4. Procedimiento para Lanzar una Nueva Versión Final (Release Oficial)

1. **Ejecutar `compilar_todo.bat` (1 solo clic, 100% automatizado)**:
   - Sube automáticamente la versión a la siguiente Final (ej: de `2.62` a `2.63`) y actualiza `updater.py` e `instalador.iss` mediante `preparar_version.py`.
   - Genera el icono oficial (`app_icon.ico`), compila con PyInstaller y empaqueta el instalador con Inno Setup en `dist_installer\Instalador_Facturador_Saint_vX.XX.exe`.
   - **Genera automáticamente el commit local en Git** (`Release vX.XX: Compilacion y actualizacion automatica de version`) incluyendo todos los archivos modificados.
2. **Subir cambios a GitHub (1 clic)**:
   - En **GitHub Desktop**, presionar **Push origin** (el commit ya fue creado por el compilador).
3. **Crear el Release en GitHub**:
   - URL: `https://github.com/betank434/bot-facturas/releases/new`
   - **Tag**: `vX.XX` (ej: `v2.63`)
   - **Título**: `Facturador Saint vX.XX`
   - **Adjunto**: Subir `dist_installer\Instalador_Facturador_Saint_vX.XX.exe`.
   - Publicar el release (NO marcar pre-release).

Al abrir cualquier cliente con una versión anterior (incluso usuarios que estén en versiones Beta), la aplicación detectará automáticamente la nueva versión final en segundo plano y ofrecerá la actualización en 1 clic.

---

## 5. Procedimiento para Compilar y Publicar Versiones Beta

Las versiones Beta trabajan directamente sobre la versión actual utilizando la nomenclatura `vX.XX.1-beta`, `vX.XX.2-beta`, etc. (ej: sobre la `2.62`, las betas son `v2.62.1-beta`, `v2.62.2-beta`), y cuando se terminen las pruebas, la versión definitiva será `v2.63`.

1. **Ejecutar `compilar_beta.bat` (1 solo clic, 100% automatizado)**:
   - Sube automáticamente la versión a la siguiente Beta (ej: `2.62.1-beta`) y la actualiza en `updater.py` e `instalador.iss`.
   - Genera el icono, compila con PyInstaller y empaqueta con Inno Setup en `dist_installer\Instalador_Facturador_Saint_vX.XX.X-beta.exe`.
   - **Genera automáticamente el commit local en Git** (`Release Beta vX.XX.X-beta: Compilacion y actualizacion automatica de version`).
2. **Subir cambios a GitHub (1 clic)**:
   - En **GitHub Desktop**, presionar **Push origin** (el commit ya fue creado por el compilador).
3. **Crear el Release Beta en GitHub**:
   - URL: `https://github.com/betank434/bot-facturas/releases/new`
   - **Tag**: `vX.XX.X-beta` (ej: `v2.62.1-beta`)
   - **Título**: `Facturador Saint vX.XX.X Beta`
   - **Casilla obligatoria**: Marcar `[X] Set as a pre-release`.
   - **Adjunto**: Subir `dist_installer\Instalador_Facturador_Saint_vX.XX.X-beta.exe`.
   - Publicar release.

**Comportamiento en clientes**:
- Al iniciar la app: **NO molestará a ningún cliente** (cero ventanas emergentes de beta al inicio).
- Al pulsar `🧪 Descargar Beta` en la cabecera: Detectará `vX.XX.X-beta` y permitirá descargarla e instalarla en 1 solo clic.



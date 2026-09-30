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

---

## 2. Dependencias del Entorno

- **Python**: 3.12+ (x64)
- **Librerías requeridas**:
  ```bash
  pip install pymupdf pyperclip pillow openpyxl pynput winocr pyinstaller
  ```
- **Compilador de Instalador**: Inno Setup 6
  - Ruta típica: `C:\Users\<Usuario>\AppData\Local\Programs\Inno Setup 6\ISCC.exe`
  - O bien: `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`

---

## 3. Reglas Críticas del Sistema (No Romper)

### A. Persistencia y Permisos en Windows (Smart Storage)
- La aplicación se instala frecuentemente en `C:\Program Files\Facturador Saint`.
- Por políticas de seguridad de Windows, usuarios estándar **NO tienen permiso de escritura** en `C:\Program Files`.
- Por tanto, la función `_resolve_storage_file(filename)` en `facturador_saint.py`:
  1. Comprueba si el archivo ya existe en `%LOCALAPPDATA%\FacturadorSaint\`. Si existe, lo usa.
  2. Si no, comprueba si `base_dir` es escribible. Si lo es, usa `base_dir`.
  3. Si `base_dir` está protegido (solo lectura), copia los archivos base a `%LOCALAPPDATA%\FacturadorSaint\` y opera allí con **100% permisos garantizados**.
- `_save_user_config()` y `_save_replacement_rules()` atrapan `PermissionError` y redirigen automáticamente a `%LOCALAPPDATA%\FacturadorSaint\`.

### B. Fusión Inteligente de Configuraciones (Smart Merge)
- **Nunca sobrescribir los ajustes del cliente en una actualización**:
  - `_load_saved_config()`: Preserva todas las opciones ya guardadas por el usuario. Si en una nueva versión se introduce una nueva clave, se agrega con su valor por defecto sin alterar nada de lo que el cliente ya haya configurado.
  - `_load_replacement_rules()`: Conserva intactos todos los códigos y sus estados (`activo: True/False`). Solo agrega un nuevo código por defecto si su `codigo_origen` no existe en la lista del cliente.

### C. Conexión SSL y Actualizador (Windows 10 / 11)
- `updater.py` utiliza `_get_ssl_context()` con `ctx.check_hostname = False` y `ctx.verify_mode = ssl.CERT_NONE`.
- Esto previene el error crítico `[SSL: CERTIFICATE_VERIFY_FAILED]` en Windows 10 y en entornos empaquetados con PyInstaller.
- El repositorio de releases es `betank434/bot-facturas`.

### D. Reglas de Inno Setup (`instalador.iss`)
- **Version Number**: `#define MyAppVersion "X.XX"` debe coincidir exactamente con `CURRENT_VERSION` en `updater.py`.
- **Exclusiones**: `[Files]` debe excluir `config_facturador.json` y `codigos_reemplazo.json` del empaquetado masivo recursivo, e instalarlos por separado con `Flags: onlyifdoesntexist; Permissions: users-full`.
- **Permisos**:
  - `[Dirs]` debe incluir `Name: "{app}"; Permissions: users-full`.
  - `[Run]` debe ejecutar `icacls.exe "{app}" /grant *S-1-5-32-545:(OI)(CI)F /T /C /Q` en modo oculto (`runhidden`) para garantizar permisos totales a todos los usuarios de Windows sin importar el idioma del sistema.
- **Acceso Directo**: Solo se crean accesos directos para la aplicación y la carpeta de PDFs. **NO crear acceso directo para `facturas_json` en el escritorio**. En `[InstallDelete]` se elimina cualquier acceso anterior a esa carpeta.

---

## 4. Procedimiento para Lanzar una Nueva Versión (Release)

1. **Incrementar la versión (Regla de oro: SIEMPRE versión nueva mayor, nunca repetir)**:
   - En `updater.py`: `CURRENT_VERSION = "X.XX"`
   - En `instalador.iss`: `#define MyAppVersion "X.XX"`
2. **Compilar ejecutable con PyInstaller**:
   ```powershell
   python build_exe.py
   ```
3. **Compilar instalador oficial con Inno Setup**:
   ```powershell
   & "C:\Users\ofici\AppData\Local\Programs\Inno Setup 6\ISCC.exe" instalador.iss
   ```
   (El instalador resultante queda en: `dist_installer\Instalador_Facturador_Saint_vX.XX.exe`).
4. **Hacer commit y push a GitHub**:
   ```powershell
   git commit -am "vX.XX: descripción del cambio"
   git push origin main
   ```
5. **Crear el Release en GitHub**:
   - URL: `https://github.com/betank434/bot-facturas/releases/new`
   - **Tag**: `vX.XX`
   - **Título**: `Facturador Saint vX.XX`
   - **Adjunto**: Subir `dist_installer\Instalador_Facturador_Saint_vX.XX.exe`.
   - Publicar el release.

Al abrir cualquier cliente con una versión anterior, la aplicación detectará automáticamente la nueva versión en segundo plano y ofrecerá la actualización en 1 clic sin tocar sus configuraciones ni datos.

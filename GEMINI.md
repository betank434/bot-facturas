# Facturador Saint Enterprise - Reglas y Guía de Desarrollo

Ver detalles completos y arquitectura en [AGENTS.md](AGENTS.md).

### Resumen Rápido para el Asistente / Agente:
1. **Repositorio**: `https://github.com/betank434/bot-facturas.git` (Owner: `betank434`, Repo: `bot-facturas`).
2. **Subir versión, Commit, Push y Release Automático (1 Clic)**: Tanto `compilar_todo.bat` como `compilar_beta.bat` incrementan automáticamente la versión en `updater.py` e `instalador.iss`, compilan el instalador, hacen `git commit` + `git push origin main` y publican el Release en GitHub (subiendo el `.exe`) automáticamente.
3. **Scripts Principales**:
   - `INSTALADOR_DEPENDENCIAS_PC.bat`: Prepara cualquier PC desde cero (Python, dependencias y herramientas).
   - `compilar_todo.bat`: Sube a la siguiente versión Final, actualiza archivos, compila, hace commit + push y publica el Release Oficial en GitHub con su `.exe`.
   - `compilar_beta.bat`: Sube a la siguiente versión Beta (`vX.XX.1-beta`), actualiza archivos, compila, hace commit + push y publica el Release Beta (`prerelease: True`) en GitHub con su `.exe`.
   - `ejecutar_facturador.bat`: Ejecución directa del código fuente con autodetección de Python.
4. **Persistencia, Permisos e Intercambio / Bloqueo de Códigos**:
   - Todo guardado de configuración usa `_resolve_storage_file()` con fallback transparente a `%LOCALAPPDATA%\FacturadorSaint\`.
   - La fusión inteligente (Smart Merge) nunca sobrescribe ajustes ni estados (`activo`) de clientes en actualizaciones; solo añade opciones o códigos nuevos.
   - En `codigos_reemplazo.json` y en la pestaña `🔄 Intercambio / 🚫 Bloqueo de Códigos` se soportan reglas de intercambio (`accion: "intercambiar"`) y de bloqueo (`accion: "bloquear"`, `codigo_destino: "BLOQUEADO"`, ej: `02206705`). Al cargar una factura JSON con códigos bloqueados, se avisa al usuario antes de facturar y se excluyen automáticamente del tipeo en Saint.
5. **Git Push y Publicación en GitHub**:
   - `preparar_version.py` obtiene el token desde Windows Credential Manager (`CredReadW`) para hacer `git push` y publicar Releases en GitHub sin bloqueos ni ventanas emergentes.
6. **Ciclo de Vida de Ventana de Auditoría**:
   - Al cerrar la auditoría (por "X" o "Cerrar Auditoría"), **NUNCA cerrar la app ni transferir foco a Saint de forma automática** (lo que ocultaría la app detrás de Saint). Mantener Facturador Saint restaurado, visible y enfocado con `forzar_ventana_al_frente(self.root)`.
7. **Motor de Auditoría OCR**:
   - Delimitadores estrictos: Cantidad (0.58 a 0.78) y Precio (0.79 a 0.915). Excluir candidatos numéricos iguales a `cantidad`. En USD omitir renglones inferiores en Bolívares (Bs) y tokens > 500. Expandir grilla inferior (`h - 32px`) para abarcar siempre el último producto.
8. **Actualizaciones Finales vs Betas**:
   - `_auto_check_updates()` al inicio NUNCA notifica betas (solo versiones finales). Las versiones Beta solo se buscan y descargan cuando el usuario pulsa deliberadamente el botón `🧪 Descargar Beta` en la cabecera.
9. **Compilación y Nomenclatura de Betas**:
   - Para versiones Beta usar `compilar_beta.bat` con nomenclatura `vX.XX.1-beta`, `vX.XX.2-beta`, etc. (ej: sobre 2.66, las betas son `v2.66.1-beta`). La versión final siguiente será `v2.67` (compilada con `compilar_todo.bat`).
10. **Formatos Soportados en `extractor.py` y Validación**:
   - Sigo (`FTC-...` / `ODC-...` con soporte dual para valores en `$` y `Bs.`), Grupo Abreu / Aikoz / Mas X Menos (`Nro OCIS...`), Norkut Cloud (`#ODC...`), Guuao (`Orden de compra #P...`) y Presupuestos Excel (`.xlsx` / `.xls`). Al presionar `⚡ Ejecutar Extractor`, si un archivo no arroja ítems, se avisa al usuario y se registra en log para evitar falsos positivos de éxito. Siempre preservar todos los formatos existentes al añadir uno nuevo.
11. **Seguridad y Privacidad**:
   - Jamás escribir tokens de GitHub en archivos ni en `.git/config` (solo lectura en RAM vía `CredReadW` en `preparar_version.py`, el cual no se incluye en `FacturadorSaint.exe`). Mantener siempre excluidos `facturas_pdf/*`, `facturas_json/*` y `cache_capturas/*` en `.gitignore` y en el instalador.




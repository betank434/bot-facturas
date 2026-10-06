# Facturador Saint Enterprise - Reglas y Guía de Desarrollo

Ver detalles completos y arquitectura en [AGENTS.md](AGENTS.md).

### Resumen Rápido para el Asistente / Agente:
1. **Repositorio**: `https://github.com/betank434/bot-facturas.git` (Owner: `betank434`, Repo: `bot-facturas`).
2. **Subir versión**: SIEMPRE incrementar la versión en `updater.py` y `instalador.iss`. NUNCA repetir una versión ya publicada en GitHub Releases.
3. **Scripts Principales**:
   - `INSTALADOR_DEPENDENCIAS_PC.bat`: Prepara cualquier PC desde cero (Python, dependencias y herramientas).
   - `compilar_todo.bat`: Compilación completa desatendida (Icono + PyInstaller + Inno Setup).
   - `ejecutar_facturador.bat`: Ejecución directa del código fuente con autodetección de Python.
4. **Persistencia y Permisos**:
   - Todo guardado de configuración usa `_resolve_storage_file()` con fallback transparente a `%LOCALAPPDATA%\FacturadorSaint\`.
   - La fusión inteligente (Smart Merge) nunca sobrescribe ajustes ni estados (`activo`) de clientes en actualizaciones; solo añade opciones o códigos nuevos.
5. **Git Push**:
   - Los commits se realizan localmente; la sincronización a GitHub se hace mediante 1 clic en GitHub Desktop (`Push origin`).
6. **Ciclo de Vida de Ventana de Auditoría**:
   - Al cerrar la auditoría (por "X" o "Cerrar Auditoría"), **NUNCA cerrar la app ni transferir foco a Saint de forma automática** (lo que ocultaría la app detrás de Saint). Mantener Facturador Saint restaurado, visible y enfocado con `forzar_ventana_al_frente(self.root)`.
7. **Motor de Auditoría OCR**:
   - Delimitadores estrictos: Cantidad (0.58 a 0.78) y Precio (0.79 a 0.915). Excluir candidatos numéricos iguales a `cantidad`. En USD omitir renglones inferiores en Bolívares (Bs) y tokens > 500. Expandir grilla inferior (`h - 32px`) para abarcar siempre el último producto.

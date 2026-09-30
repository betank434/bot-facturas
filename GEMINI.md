# Facturador Saint Enterprise - Reglas y Guía de Desarrollo

Ver detalles completos y arquitectura en [AGENTS.md](file:///c:/Users/ofici/Desktop/bot%20facturas%20sigo/bot%20facturas/AGENTS.md).

### Resumen Rápido para el Agente:
1. **Repositorio**: `https://github.com/betank434/bot-facturas.git` (Owner: `betank434`, Repo: `bot-facturas`).
2. **Subir versión**: SIEMPRE incrementar la versión en `updater.py` y `instalador.iss`. NUNCA repetir una versión ya publicada.
3. **Compilación**:
   - `python build_exe.py`
   - Inno Setup `ISCC.exe instalador.iss`
4. **Persistencia**:
   - Todo guardado de configuración usa `_resolve_storage_file()` con fallback a `%LOCALAPPDATA%\FacturadorSaint\`.
   - La fusión inteligente nunca sobrescribe ajustes ni estados (`activo`) de clientes en actualizaciones; solo añade opciones o códigos nuevos.

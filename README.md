# Facturador Saint Enterprise

Automatización inteligente de facturación para **Saint Annual Enterprise** a partir de facturas en formato PDF.

---

## 🚀 Inicio Rápido en Cualquier PC

### 1. Configurar Entorno en 1 Clic
Ejecuta el archivo:
```bat
INSTALADOR_DEPENDENCIAS_PC.bat
```
Este script se encarga de:
- Verificar e instalar Python 3.12 si no está en el equipo.
- Restaurar `pip` automáticamente si está ausente.
- Instalar todas las dependencias necesarias (`pymupdf`, `pyperclip`, `pillow`, `openpyxl`, `pynput`, `winocr`, `pyinstaller`).
- Instalar Inno Setup 6 si vas a compilar instaladores en esa máquina.

### 2. Ejecutar la Aplicación
```bat
ejecutar_facturador.bat
```
O directamente con Python:
```bash
python facturador_saint.py
```

### 3. Compilar y Publicar Release en GitHub en 1 Clic
```bat
compilar_todo.bat
```
*(O `compilar_beta.bat` para versiones Beta)*.
- Incrementa automáticamente la versión en `updater.py` e `instalador.iss`.
- Compila el ejecutable e instalador en `dist_installer/`.
- Crea el commit local, hace `git push origin main` y publica el Release en GitHub (subiendo el instalador `.exe`) de forma 100% automática.

---

## 🛠️ Arquitectura y Características

- **Extracción Multiformato (PDF y Excel)**: Extracción de alta precisión con PyMuPDF y `openpyxl` para Sigo (`FTC` / `ODC`), Grupo Abreu / Hiper Ahorro Aikoz / Mas X Menos (`OCIS`), Norkut Cloud (`#ODC`), Guuao y presupuestos Excel (`.xlsx` / `.xls`), con normalización automática de códigos de barra a 8 y 12 dígitos.
- **Motor de Teclado Saint**: Inyección de eventos a nivel de sistema mediante `pynput` y `ctypes`, con soporte de atajos globales (`F8`: Iniciar, `F7`: Pausar, `F12`: Detener).
- **Auditoría OCR en Tiempo Real**: Validación multinivel mediante `winocr` nativo de Windows 10/11. Panel detallado de discrepancias (faltantes, ajenos y diferencias de precio en USD vs Bs) con ciclo de vida seguro que preserva la visibilidad y foco de Facturador Saint.
- **Intercambio y Bloqueo de Códigos (`🚫 No Facturar`)**: Pestaña integrada para intercambiar códigos equivalentes o bloquear productos específicos (ej. `02206705`) con alerta preventiva automática al cargar facturas JSON antes de iniciar la facturación.
- **Persistencia Inteligente**: Configuración guardada a prueba de fallos de permisos en Windows (compatible con `C:\Program Files` mediante `%LOCALAPPDATA%\FacturadorSaint`).
- **Fusión Inteligente (Smart Merge)**: Las actualizaciones preservan 100% de los ajustes y códigos activos de cada cliente, agregando solo nuevas opciones.
- **Actualizador y Publicador 1-Clic**: Detección y descarga automática de versiones vía GitHub Releases (`betank434/bot-facturas`), y publicación desatendida desde los compiladores usando el Administrador de Credenciales de Windows sin exponer tokens en código y aislando siempre las facturas locales.

Para detalles de arquitectura y reglas del proyecto, consultar [AGENTS.md](AGENTS.md).

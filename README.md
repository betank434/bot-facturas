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

### 3. Compilar Ejecutable e Instalador Oficial
```bat
compilar_todo.bat
```
El instalador generado se guardará en la carpeta `dist_installer/`.

---

## 🛠️ Arquitectura y Características

- **Extracción de PDF**: Extracción de alta precisión con PyMuPDF y motor regex personalizado para formatos de facturas electrónicas.
- **Motor de Teclado Saint**: Inyección de eventos a nivel de sistema mediante `pynput` y `ctypes`, con soporte de atajos globales (`F8`: Iniciar, `F7`: Pausar, `F12`: Detener).
- **OCR de Validación**: Reconocimiento de precios y renglones en tiempo real mediante `winocr` nativo de Windows 10/11.
- **Persistencia Inteligente**: Configuración guardada a prueba de fallos de permisos en Windows (compatible con `C:\Program Files` mediante `%LOCALAPPDATA%\FacturadorSaint`).
- **Fusión Inteligente (Smart Merge)**: Las actualizaciones preservan 100% de los ajustes y códigos activos de cada cliente, agregando solo nuevas opciones.
- **Actualizador 1-Clic**: Detección y descarga automática de versiones vía GitHub Releases (`betank434/bot-facturas`).

Para detalles de arquitectura y reglas del proyecto, consultar [AGENTS.md](file:///c:/Users/ofici/Desktop/bot%20facturas%20sigo/bot%20facturas/AGENTS.md).

@echo off
setlocal EnableDelayedExpansion
title CONFIGURADOR DE ENTORNO - FACTURADOR SAINT ENTERPRISE
color 0B

echo ================================================================
echo    INSTALADOR AUTOMATICO DE ENTORNO Y DEPENDENCIAS (WINDOWS)
echo                  PROYECTO: FACTURADOR SAINT
echo ================================================================
echo.

:: 1. Verificar si Python está instalado
echo [1/4] Verificando instalacion de Python...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [AVISO] Python no esta detectado en el PATH del sistema.
    echo Intentando instalar Python 3.12 automaticamente con winget...
    winget --version >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo Ejecutando: winget install Python.Python.3.12...
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        echo.
        echo [IMPORTANTE] Por favor cierra y vuelve a abrir este archivo .bat
        echo para que Windows reconozca el nuevo comando 'python'.
        pause
        exit /b 0
    ) else (
        echo [ERROR] No se pudo encontrar 'winget'.
        echo Por favor descarga e instala Python 3.12 manualmente desde:
        echo https://www.python.org/downloads/
        echo **RECUERDA MARCAR LA CASILLA: "Add python.exe to PATH"**
        pause
        exit /b 1
    )
) else (
    for /f "tokens=*" %%i in ('python --version') do echo [OK] %%i detectado correctamente.
)
echo.

:: 2. Actualizar PIP
echo [2/4] Actualizando instalador de paquetes de Python (pip)...
python -m pip install --upgrade pip
echo.

:: 3. Instalar librerías del proyecto
echo [3/4] Instalando librerias requeridas de Python...
echo       - pymupdf (lectura y extraccion de facturas PDF)
echo       - pyperclip (intercambio veloz con portapapeles)
echo       - pillow (procesamiento de imagenes)
echo       - openpyxl (soporte y auditoria Excel)
echo       - pynput (control y atajos de teclado F8, F7, F12)
echo       - winocr (OCR nativo de Windows 10/11 sin dependencias externas)
echo       - pyinstaller (compilacion a ejecutable .exe nativo)
echo.
python -m pip install -r "%~dp0requirements.txt"
if %ERRORLEVEL% NEQ 0 (
    echo [AVISO] Reintentando instalacion directa de paquetes...
    python -m pip install pymupdf pyperclip pillow openpyxl pynput winocr pyinstaller
)
echo.

:: 4. Verificación de herramientas complementarias
echo [4/4] Verificando Inno Setup 6 (para compilar instaladores)...
set INNO_FOUND=0
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set INNO_FOUND=1
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set INNO_FOUND=1
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set INNO_FOUND=1

if %INNO_FOUND% EQU 1 (
    echo [OK] Inno Setup 6 encontrado en el equipo.
) else (
    echo [INFO] Inno Setup 6 no esta instalado en las rutas habituales.
    echo        Nota: Solo es necesario si vas a compilar instaladores en esta PC.
    echo Deseas instalar Inno Setup 6 ahora mismo mediante winget? [S/N]
    set /p INST_INNO="Opcion - presiona S y Enter para instalar, o N para omitir: "
    if /i "!INST_INNO!"=="S" (
        echo Instalando Inno Setup 6...
        winget install InnoSetup.InnoSetup --accept-package-agreements --accept-source-agreements
    )
)
echo.

:: 5. Verificación final de librerías en Python
echo ================================================================
echo             VERIFICACION FINAL DEL ENTORNO PYTHON
echo ================================================================
python -c "import pymupdf, pyperclip, PIL, openpyxl, pynput, winocr, PyInstaller; print('[OK] TODAS LAS LIBRERIAS SE CARGARON CORRECTAMENTE')"
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ================================================================
    echo        ENHORABUENA: Tu PC esta 100%% configurada y lista!
    echo ================================================================
    echo.
    echo - Para iniciar el programa:
    echo     python facturador_saint.py
    echo.
    echo - Para compilar el ejecutable y el instalador:
    echo     compilar_todo.bat
    echo.
) else (
    echo.
    echo [ADVERTENCIA] Algunas librerias arrojaron error al verificarse.
    echo Revisa la salida de pip arriba para comprobar los detalles.
)

echo Presiona cualquier tecla para finalizar.
pause >nul

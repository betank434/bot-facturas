@echo off
setlocal EnableDelayedExpansion
title CONFIGURADOR DE ENTORNO - FACTURADOR SAINT ENTERPRISE
color 0B

echo ================================================================
echo    INSTALADOR AUTOMATICO DE ENTORNO Y DEPENDENCIAS (WINDOWS)
echo                  PROYECTO: FACTURADOR SAINT
echo ================================================================
echo.

:: 1. Detección Inteligente de Python
echo [1/4] Buscando instalacion oficial de Python en el equipo...

set "PYTHON_CMD="

:: Prioridad A: Lanzador oficial de Windows 'py -3'
py -3 --version >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    set "PYTHON_CMD=py -3"
    goto :PYTHON_SELECCIONADO
)

:: Prioridad B: Rutas estandar de Python oficial en Windows
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%ProgramFiles%\Python312\python.exe"
    "%ProgramFiles%\Python311\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
) do (
    if exist "%%~P" (
        set "PYTHON_CMD="%%~P""
        goto :PYTHON_SELECCIONADO
    )
)

:: Prioridad C: Buscar en el PATH evitando venvs de otras apps (ej: hermes-agent)
for /f "delims=" %%I in ('where.exe python 2^>nul') do (
    echo %%I | findstr /i /c:"hermes" /c:"Temp" >nul
    if !ERRORLEVEL! NEQ 0 (
        set "PYTHON_CMD="%%I""
        goto :PYTHON_SELECCIONADO
    )
)

:: Prioridad D: Cualquier python disponible en el sistema
for /f "delims=" %%I in ('where.exe python 2^>nul') do (
    set "PYTHON_CMD="%%I""
    goto :PYTHON_SELECCIONADO
)

:PYTHON_SELECCIONADO
if not defined PYTHON_CMD (
    echo [AVISO] No se encontro ninguna version de Python instalada.
    echo Intentando instalar Python 3.12 automaticamente mediante winget...
    winget --version >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        echo.
        echo [IMPORTANTE] Por favor cierra y vuelve a abrir este instalador .bat
        echo para que Windows actualice las variables de entorno.
        pause
        exit /b 0
    ) else (
        echo [ERROR] No se pudo encontrar 'winget'.
        echo Descarga e instala Python 3.12 manualmente desde:
        echo https://www.python.org/downloads/
        echo [NOTA] Recuerda marcar la casilla: Add python.exe to PATH
        pause
        exit /b 1
    )
)

for /f "delims=" %%V in ('%PYTHON_CMD% --version 2^>^&1') do echo [OK] Usando %%V en: %PYTHON_CMD%
echo.

:: 2. Verificar y Reparar PIP si no existe (Solución a 'No module named pip')
echo [2/4] Verificando instalador de paquetes - pip...
%PYTHON_CMD% -m pip --version >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [AVISO] El entorno de Python seleccionado no tiene pip instalado.
    echo         Restaurando pip automaticamente con ensurepip...
    %PYTHON_CMD% -m ensurepip --default-pip >nul 2>&1
    %PYTHON_CMD% -m pip --version >nul 2>&1
    if !ERRORLEVEL! NEQ 0 (
        echo         Descargando e instalando pip oficial via get-pip.py...
        powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://bootstrap.pypa.io/get-pip.py', '$env:TEMP\get-pip.py')"
        %PYTHON_CMD% "%TEMP%\get-pip.py" --quiet
    )
)

echo Actualizando pip a la ultima version...
%PYTHON_CMD% -m pip install --upgrade pip --quiet
for /f "delims=" %%P in ('%PYTHON_CMD% -m pip --version 2^>^&1') do echo [OK] %%P
echo.

:: 3. Instalar librerías del proyecto
echo [3/4] Instalando librerias requeridas de Python...
echo       - pymupdf (extraccion de facturas PDF)
echo       - pyperclip (comunicacion con portapapeles)
echo       - pillow (procesamiento de imagenes de articulos)
echo       - openpyxl (soporte y generacion de reportes Excel)
echo       - pynput (control y atajos F8, F7, F12)
echo       - winocr (OCR nativo de Windows 10/11 sin dependencias externas)
echo       - pyinstaller (compilacion a ejecutable .exe nativo)
echo.

if exist "%~dp0requirements.txt" (
    %PYTHON_CMD% -m pip install -r "%~dp0requirements.txt"
) else (
    %PYTHON_CMD% -m pip install pymupdf pyperclip pillow openpyxl pynput winocr pyinstaller
)

if !ERRORLEVEL! NEQ 0 (
    echo [AVISO] Reintentando instalacion directa paquete por paquete...
    %PYTHON_CMD% -m pip install pymupdf pyperclip pillow openpyxl pynput winocr pyinstaller
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
    set "PRIMERA_LETRA=!INST_INNO:~0,1!"
    if /i "!PRIMERA_LETRA!"=="S" (
        echo Instalando Inno Setup 6 con winget...
        winget install InnoSetup.InnoSetup --accept-package-agreements --accept-source-agreements
    ) else if /i "!PRIMERA_LETRA!"=="Y" (
        echo Instalando Inno Setup 6 con winget...
        winget install InnoSetup.InnoSetup --accept-package-agreements --accept-source-agreements
    )
)
echo.

:: 5. Verificación final de librerías en Python
echo ================================================================
echo             VERIFICACION FINAL DEL ENTORNO PYTHON
echo ================================================================
%PYTHON_CMD% -c "import pymupdf, pyperclip, PIL, openpyxl, pynput, winocr, PyInstaller; print('[OK] TODAS LAS LIBRERIAS SE CARGARON CORRECTAMENTE')"
if !ERRORLEVEL! EQU 0 (
    echo.
    echo ================================================================
    echo        ENHORABUENA: Tu PC esta 100%% configurada y lista!
    echo ================================================================
    echo.
    echo - Para iniciar el programa:
    echo     %PYTHON_CMD% facturador_saint.py
    echo.
    echo - Para compilar el ejecutable y el instalador:
    echo     compilar_todo.bat
    echo.
) else (
    echo.
    echo [ADVERTENCIA] Algunas librerias arrojaron error al verificarse.
    echo Revisa los mensajes de error superiores.
)

echo Presiona cualquier tecla para finalizar.
pause >nul

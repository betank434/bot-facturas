@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Compilador de Versiones Beta de Facturador Saint

echo ========================================================
echo   COMPILADOR DE VERSIONES BETA - FACTURADOR SAINT
echo ========================================================
echo.

:: 1. Detectar Python correcto (evitando entornos virtuales de terceros como hermes-agent)
set "PYTHON_CMD="

py -3 --version >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    set "PYTHON_CMD=py -3"
    goto :PYTHON_OK
)

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
        goto :PYTHON_OK
    )
)

for /f "delims=" %%I in ('where.exe python 2^>nul') do (
    echo %%I | findstr /i /c:"hermes" /c:"Temp" >nul
    if !ERRORLEVEL! NEQ 0 (
        set "PYTHON_CMD="%%I""
        goto :PYTHON_OK
    )
)

for /f "delims=" %%I in ('where.exe python 2^>nul') do (
    set "PYTHON_CMD="%%I""
    goto :PYTHON_OK
)

:PYTHON_OK
if not defined PYTHON_CMD (
    echo [ERROR] No se encontro Python en el sistema.
    echo Por favor ejecuta primero INSTALADOR_DEPENDENCIAS_PC.bat
    pause
    exit /b 1
)

:: 2. Auto-verificar si PyInstaller está instalado
%PYTHON_CMD% -c "import PyInstaller" >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [AVISO] PyInstaller no esta instalado. Instalando...
    %PYTHON_CMD% -m pip install pyinstaller
)

:: 3. Obtener sugerencia de próxima versión beta
for /f "delims=" %%V in ('%PYTHON_CMD% preparar_version.py --next-beta') do set "SUGGESTED_BETA=%%V"
for /f "delims=" %%C in ('%PYTHON_CMD% preparar_version.py --current') do set "CURRENT_VER=%%C"

echo Version actual en el sistema: %CURRENT_VER%
echo Proxima version Beta recomendada: %SUGGESTED_BETA%
echo.

set "TARGET_BETA="
if "%~1"=="" (
    set /p "TARGET_BETA=Introduce version Beta [Presiona ENTER para usar %SUGGESTED_BETA%]: "
) else (
    set "TARGET_BETA=%~1"
)

if "!TARGET_BETA!"=="" set "TARGET_BETA=%SUGGESTED_BETA%"

echo.
echo -> Estableciendo version Beta: !TARGET_BETA! ...
%PYTHON_CMD% preparar_version.py --set !TARGET_BETA!
if !ERRORLEVEL! NEQ 0 (
    echo Error al actualizar archivos de version.
    pause
    exit /b 1
)

:: 4. Compilar icono, ejecutable e instalador
echo.
echo Paso 1: Generando icono oficial app_icon.ico...
%PYTHON_CMD% crear_icono.py
if !ERRORLEVEL! NEQ 0 (
    echo Error al generar icono.
    pause
    exit /b !ERRORLEVEL!
)

echo.
echo Paso 2: Compilando FacturadorSaint.exe con PyInstaller...
%PYTHON_CMD% build_exe.py
if !ERRORLEVEL! NEQ 0 (
    echo Error al compilar ejecutable con PyInstaller.
    pause
    exit /b !ERRORLEVEL!
)

echo.
echo Paso 3: Generando Instalador con Inno Setup...
set "ISCC="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    for /f "delims=" %%I in ('where.exe ISCC.exe 2^>nul') do set "ISCC=%%I"
)

if not defined ISCC (
    echo.
    echo [ERROR] No se pudo encontrar Inno Setup 6 (ISCC.exe).
    echo Por favor descargalo e instalalo desde https://jrsoftware.org/isdl.php
    pause
    exit /b 1
)

"%ISCC%" instalador.iss
if !ERRORLEVEL! NEQ 0 (
    echo Error al generar el instalador con Inno Setup.
    pause
    exit /b !ERRORLEVEL!
)

echo.
echo ========================================================
echo   COMPILACION DE VERSION BETA EXITOSA!
echo   Instalador: dist_installer\Instalador_Facturador_Saint_v!TARGET_BETA!.exe
echo ========================================================
echo.
echo Pasos para publicar esta Beta en GitHub:
echo   1. Abre GitHub Desktop y presiona 'Push origin'.
echo   2. Ve a: https://github.com/betank434/bot-facturas/releases/new
echo   3. Tag:    v!TARGET_BETA!
echo   4. Titulo: Facturador Saint v!TARGET_BETA!
echo   5. Marca la casilla: [X] Set as a pre-release
echo   6. Adjunta el archivo: dist_installer\Instalador_Facturador_Saint_v!TARGET_BETA!.exe
echo   7. Pulsa 'Publish release'.
echo.
echo Tus clientes en v2.61 podran descargar esta beta pulsando 'Descargar Beta'.
echo ========================================================
pause

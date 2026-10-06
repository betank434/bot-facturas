@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Compilador de Facturador Saint (.exe + Instalador)

echo ========================================================
echo   COMPILANDO FACTURADOR SAINT (.EXE + INSTALADOR)
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

for /f "delims=" %%C in ('%PYTHON_CMD% preparar_version.py --current 2^>nul') do set "COMPILING_VER=%%C"
if defined COMPILING_VER echo Version a compilar: %COMPILING_VER%
echo.

:: 2. Auto-verificar si PyInstaller está instalado, y si falta instalarlo de inmediato
%PYTHON_CMD% -c "import PyInstaller" >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [AVISO] PyInstaller no esta instalado en este Python.
    echo Instalando librerias necesarias automaticamente...
    if exist "%~dp0requirements.txt" (
        %PYTHON_CMD% -m pip install -r "%~dp0requirements.txt"
    ) else (
        %PYTHON_CMD% -m pip install pymupdf pyperclip pillow openpyxl pynput winocr pyinstaller
    )
    if !ERRORLEVEL! NEQ 0 (
        %PYTHON_CMD% -m pip install pyinstaller
    )
)

echo.
echo Paso 1: Generando icono oficial app_icon.ico...
%PYTHON_CMD% crear_icono.py
if %ERRORLEVEL% NEQ 0 (
    echo Error al generar icono.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Paso 2: Compilando FacturadorSaint.exe con PyInstaller...
%PYTHON_CMD% build_exe.py
if %ERRORLEVEL% NEQ 0 (
    echo Error al compilar ejecutable con PyInstaller.
    pause
    exit /b %ERRORLEVEL%
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
    echo [AVISO] Inno Setup 6 no esta instalado en este equipo.
    echo Instalando Inno Setup 6 automaticamente...
    winget install JRSoftware.InnoSetup --accept-package-agreements --accept-source-agreements
    
    :: Si winget falla o no tiene catalogo actualizado, descargar directamente
    if !ERRORLEVEL! NEQ 0 (
        echo [INFO] Descargando instalador oficial de Inno Setup...
        powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe', '$env:TEMP\innosetup.exe'); Start-Process '$env:TEMP\innosetup.exe' -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-' -Wait"
    )
    
    :: Volver a buscar ISCC.exe tras la instalacion
    if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
    if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
    if not defined ISCC (
        for /f "delims=" %%I in ('where.exe ISCC.exe 2^>nul') do set "ISCC=%%I"
    )
)

if not defined ISCC (
    echo.
    echo [ERROR] No se pudo encontrar o instalar Inno Setup 6.
    echo Por favor descargalo e instalalo manualmente desde:
    echo https://jrsoftware.org/isdl.php
    pause
    exit /b 1
)

"%ISCC%" instalador.iss
if %ERRORLEVEL% NEQ 0 (
    echo Error al generar el instalador con Inno Setup.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ========================================================
echo   COMPILACION Y GENERACION DE INSTALADOR EXITOSA!
echo   Ubicacion: dist_installer\
echo ========================================================
pause

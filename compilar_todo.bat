@echo off
cd /d "%~dp0"
title Compilador de Facturador Saint (.exe + Instalador)
echo ========================================================
echo   COMPILANDO FACTURADOR SAINT (.EXE + INSTALADOR)
echo ========================================================
echo.
echo Paso 1: Generando icono oficial app_icon.ico...
python crear_icono.py
if %ERRORLEVEL% NEQ 0 (
    echo Error al generar icono.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Paso 2: Compilando FacturadorSaint.exe con PyInstaller...
python build_exe.py
if %ERRORLEVEL% NEQ 0 (
    echo Error al compilar ejecutable con PyInstaller.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Paso 3: Generando Instalador con Inno Setup...
set "ISCC=C:\Users\ofici\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    for /f "tokens=*" %%i in ('where ISCC.exe 2^>nul') do set "ISCC=%%i"
)

if not exist "%ISCC%" (
    echo No se encontro ISCC.exe de Inno Setup en el sistema.
    pause
    exit /b 1
)

"%ISCC%" instalador.iss
if %ERRORLEVEL% NEQ 0 (
    echo Error al generar el instalador con Inno Setup.
    pause
    exit /b %ERRORLEVEL%
)

copy /y "dist_installer\Instalador_Facturador_Saint_v2.4.exe" "Instalador_Facturador_Saint_v2.4.exe" >nul
echo.
echo ========================================================
echo   COMPILACION Y GENERACION DE INSTALADOR EXITOSA!
echo   Instalador: Instalador_Facturador_Saint_v2.4.exe
echo ========================================================
pause

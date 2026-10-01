@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Facturador Automatico Saint

set "PYTHON_CMD="
py -3 --version >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    set "PYTHON_CMD=py -3"
    goto :RUN
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
        goto :RUN
    )
)

for /f "delims=" %%I in ('where.exe python 2^>nul') do (
    echo %%I | findstr /i /c:"hermes" /c:"Temp" >nul
    if !ERRORLEVEL! NEQ 0 (
        set "PYTHON_CMD="%%I""
        goto :RUN
    )
)

for /f "delims=" %%I in ('where.exe python 2^>nul') do (
    set "PYTHON_CMD="%%I""
    goto :RUN
)

:RUN
if not defined PYTHON_CMD set "PYTHON_CMD=python"

%PYTHON_CMD% facturador_saint.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Ocurrio un error al ejecutar la aplicacion.
    echo Asegurate de haber ejecutado antes INSTALADOR_DEPENDENCIAS_PC.bat
    pause
)

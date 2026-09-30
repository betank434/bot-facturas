@echo off
cd /d "%~dp0"
title Facturador Automatico Saint
python facturador_saint.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Ocurrio un error al ejecutar.
    pause
)

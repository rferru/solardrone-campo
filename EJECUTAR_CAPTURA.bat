@echo off
REM Lanzador del Sistema de Captura Solar Drone v5
REM Doble-click en este archivo para arrancar la captura

cd /d "%~dp0"

REM Verificar que config.json existe
if not exist "config.json" (
    echo.
    echo ERROR: No se encontro config.json
    echo Ejecuta primero EJECUTAR_CONFIGURADOR.bat
    echo.
    pause
    exit /b 1
)

echo ================================================
echo  SOLAR DRONE - Sistema de Captura v5
echo ================================================
echo.

python captura_v5.py

echo.
echo La captura se ha cerrado. Revisa log.txt si hubo errores.
pause

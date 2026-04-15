@echo off
REM Lanzador del Configurador de escaneres
REM Usar UNA VEZ al principio para asignar puertos COM a cada escaner

cd /d "%~dp0"

echo ================================================
echo  SOLAR DRONE - Configurador v5
echo ================================================
echo.

python configurador_v5.py

echo.
pause

@echo off
REM Sube las capturas a Google Cloud Storage cuando haya wifi.
REM Requisitos: gsutil instalado y autenticado (gcloud auth login).
REM Bucket: gs://balbona-campo (creado por Rubén)

cd /d "%~dp0"

echo ================================================
echo  SUBIR DATOS A GCS
echo ================================================
echo.

REM Comprobar internet rapido
ping -n 1 -w 1500 8.8.8.8 >nul 2>&1
if errorlevel 1 (
    echo ERROR: No hay internet. Conecta el wifi y vuelve a ejecutar.
    pause
    exit /b 1
)

echo Internet OK. Subiendo carpeta capturas\ ...
echo.

REM rsync recursivo, solo cosas nuevas
gsutil -m rsync -r capturas gs://balbona-campo/capturas

if errorlevel 1 (
    echo.
    echo ATENCION: La subida tuvo errores. Revisa arriba.
) else (
    echo.
    echo OK - Subida completa.
)

echo.
pause

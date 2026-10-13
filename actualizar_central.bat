@echo off
REM CENTRAL - procesa las bases de los dashboards, valida contra ellos y publica los JSON del portal.
REM Uso: doble clic, o "actualizar_central.bat --simular" para solo validar.
chcp 65001 >nul
cd /d "%~dp0"

python etl\central_etl.py procesar %*
if errorlevel 1 (
  echo.
  echo El ETL terminó con errores. Revise los mensajes anteriores.
  pause
  exit /b 1
)

echo.
echo Validando contra los dashboards...
python etl\validar_dashboards.py

echo.
echo Revise data\cargas\errores\ si hubo registros rechazados.
echo Para publicar en GitHub Pages:
echo     git add data
echo     git commit -m "Actualiza datos CENTRAL"
echo     git push
pause

@echo off
REM Calidad A365 - cambiar las contraseñas de los perfiles y volver a cifrar los datos.
chcp 65001 >nul
cd /d "%~dp0"
python etl\perfiles.py editar
echo.
pause

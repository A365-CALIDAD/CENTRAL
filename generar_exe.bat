@echo off
REM Genera CalidadA365.exe (no necesita Python en el PC donde se use).
REM El .exe debe quedar dentro de la carpeta CENTRAL, junto a config\ y data\.
chcp 65001 >nul
cd /d "%~dp0"
py -m PyInstaller --clean --onefile --console --noconfirm --name CalidadA365 ^
  --icon "%~dp0assets\img\icono.ico" ^
  --distpath . --workpath "%TEMP%\calidada365_build" --specpath "%TEMP%\calidada365_build" ^
  --paths etl --hidden-import central_etl --hidden-import perfiles --hidden-import avisos --hidden-import validar_dashboards ^
  --collect-all openpyxl --collect-submodules pandas --collect-submodules cryptography ^
  --exclude-module matplotlib --exclude-module tkinter --exclude-module selenium --exclude-module IPython ^
  etl\menu.py
echo.
pause

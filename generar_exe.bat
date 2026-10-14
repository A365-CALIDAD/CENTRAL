@echo off
REM Genera CalidadA365.exe (menu) y CalidadA365_Actualizar.exe (actualiza y publica sin menu).
REM No necesitan Python en el PC donde se usen. Deben quedar en la carpeta CENTRAL, junto a config\ y data\.
chcp 65001 >nul
cd /d "%~dp0"
set "SALIDA=%TEMP%\calidada365_dist"
py -m PyInstaller --clean --onefile --console --noconfirm --name CalidadA365 ^
  --icon "%~dp0assets\img\icono.ico" ^
  --distpath "%SALIDA%" --workpath "%TEMP%\calidada365_build" --specpath "%TEMP%\calidada365_build" ^
  --paths etl --hidden-import central_etl --hidden-import perfiles --hidden-import avisos --hidden-import validar_dashboards ^
  --collect-all openpyxl --collect-submodules pandas --collect-submodules cryptography ^
  --exclude-module matplotlib --exclude-module tkinter --exclude-module selenium --exclude-module IPython ^
  etl\menu.py
if errorlevel 1 (
  echo No se pudo generar el ejecutable.
  pause
  exit /b 1
)
REM El mismo programa con nombre "_Actualizar" arranca directo en modo automatico.
copy /Y "%SALIDA%\CalidadA365.exe" "%~dp0CalidadA365.exe" >nul || echo Cierra CalidadA365.exe e intenta de nuevo.
copy /Y "%SALIDA%\CalidadA365.exe" "%~dp0CalidadA365_Actualizar.exe" >nul || echo Cierra CalidadA365_Actualizar.exe e intenta de nuevo.
echo.
echo Listo: CalidadA365.exe y CalidadA365_Actualizar.exe
pause

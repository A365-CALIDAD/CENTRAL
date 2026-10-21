@echo off
REM Genera los programas de Calidad A365. No necesitan Python en el PC donde se usen.
REM Deben quedar en la carpeta CENTRAL, junto a config\ y data\.
REM   CalidadA365.exe             menu de administracion (KPI, contrasenas, avisos, bitacora...)
REM   CalidadA365_Actualizar.exe  el mismo, sin menu: actualiza los KPI y publica (tarea diaria)
REM   AvanceEquipo.exe            programa aparte, solo Avance equipo (tarea de cada hora)
chcp 65001 >nul
cd /d "%~dp0"
set "SALIDA=%TEMP%\calidada365_dist"
set "COMUN=--paths etl --hidden-import central_etl --hidden-import perfiles --hidden-import avance --hidden-import qualtrics --collect-data tzdata --collect-all openpyxl --collect-submodules pandas --collect-submodules cryptography --exclude-module matplotlib --exclude-module tkinter --exclude-module IPython"
py -m PyInstaller --clean --onefile --console --noconfirm --name CalidadA365 ^
  --icon "%~dp0assets\img\icono.ico" ^
  --distpath "%SALIDA%" --workpath "%TEMP%\calidada365_build" --specpath "%TEMP%\calidada365_build" ^
  %COMUN% --hidden-import avisos --hidden-import validar_dashboards --exclude-module selenium ^
  etl\menu.py
if errorlevel 1 goto error
py -m PyInstaller --clean --onefile --console --noconfirm --name AvanceEquipo ^
  --icon "%~dp0assets\img\icono.ico" ^
  --distpath "%SALIDA%" --workpath "%TEMP%\calidada365_build" --specpath "%TEMP%\calidada365_build" ^
  %COMUN% --hidden-import menu --hidden-import descarga_entel ^
  --collect-all selenium --hidden-import dotenv --hidden-import win32com.client --hidden-import win32process --hidden-import win32gui ^
  etl\avance_equipo.py
if errorlevel 1 goto error
REM El mismo menu con nombre "_Actualizar" arranca directo en modo automatico.
copy /Y "%SALIDA%\CalidadA365.exe" "%~dp0CalidadA365.exe" >nul || echo Cierra CalidadA365.exe e intenta de nuevo.
copy /Y "%SALIDA%\CalidadA365.exe" "%~dp0CalidadA365_Actualizar.exe" >nul || echo Cierra CalidadA365_Actualizar.exe e intenta de nuevo.
copy /Y "%SALIDA%\AvanceEquipo.exe" "%~dp0AvanceEquipo.exe" >nul || echo Cierra AvanceEquipo.exe e intenta de nuevo.
echo.
echo Listo: CalidadA365.exe, CalidadA365_Actualizar.exe y AvanceEquipo.exe
pause
exit /b 0
:error
echo No se pudo generar el ejecutable.
pause
exit /b 1

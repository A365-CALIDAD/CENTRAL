@echo off
REM Calidad A365 - programa la extraccion de cada hora del modulo Avance equipo (solo ese modulo, rapido).
REM Crea la tarea "Calidad A365 - Avance equipo", que ejecuta CalidadA365_Avance.exe (sin menu).
REM Los KPI siguen con programar_actualizacion.bat (ej. una vez al dia). Uso: doble clic, o:  programar_avance.bat 08:30 1 12
REM      (primera hora del dia, repetir cada N horas -0 = una vez al dia-, durante M horas)
chcp 65001 >nul
setlocal
set "EXE=%~dp0CalidadA365_Avance.exe"
set "TAREA=Calidad A365 - Avance equipo"

if not exist "%EXE%" (
  echo No se encontro CalidadA365_Avance.exe en esta carpeta.
  pause
  exit /b 1
)

set "HORA=%~1"
set "CADA=%~2"
set "HASTA=%~3"
if not "%HORA%"=="" goto crear

echo.
echo Programar la extraccion de Avance equipo (cada hora)
echo -----------------------------------------------------
echo Antes, abre CalidadA365.exe y usa "Solo publicar" una vez para dejar guardados
echo tu nombre y correo de Git y la sesion de GitHub.
echo.
set /p "HORA=Hora de la primera extraccion del dia (HH:MM, ej. 08:30): "
set /p "CADA=Repetir cada cuantas horas (0 = solo una vez al dia): "
set /p "HASTA=Durante cuantas horas desde la primera (ej. 10): "

:crear
if "%CADA%"=="" set "CADA=0"
if "%HASTA%"=="" set "HASTA=12"
schtasks /Delete /TN "%TAREA%" /F >nul 2>&1
if "%CADA%"=="0" goto una_vez
set /a MINUTOS=%CADA%*60
schtasks /Create /TN "%TAREA%" /TR "\"%EXE%\"" /SC DAILY /ST %HORA% /RI %MINUTOS% /DU %HASTA%:00 /F
goto resultado

:una_vez
schtasks /Create /TN "%TAREA%" /TR "\"%EXE%\"" /SC DAILY /ST %HORA% /F

:resultado
if errorlevel 1 (
  echo.
  echo No se pudo crear la tarea. Revisa la hora ^(HH:MM^) y los numeros ingresados.
) else (
  echo.
  echo Tarea creada: "%TAREA%".
  echo Cada ejecucion queda registrada en logs\automatico.log
  echo Para quitarla:  schtasks /Delete /TN "%TAREA%" /F
)
if "%~1"=="" pause
endlocal

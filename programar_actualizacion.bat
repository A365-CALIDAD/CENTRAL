@echo off
REM Calidad A365 - programa la actualizacion y publicacion automatica en el Programador de tareas de Windows.
REM Crea la tarea "Calidad A365 - Actualizar y publicar", que ejecuta CalidadA365_Actualizar.exe (sin menu).
REM Uso: doble clic y responder las preguntas, o:  programar_actualizacion.bat 08:30 4 10
REM      (primera hora del dia, repetir cada N horas -0 = una vez al dia-, durante M horas)
chcp 65001 >nul
setlocal
set "EXE=%~dp0CalidadA365_Actualizar.exe"
set "TAREA=Calidad A365 - Actualizar y publicar"

if not exist "%EXE%" (
  echo No se encontro CalidadA365_Actualizar.exe en esta carpeta.
  pause
  exit /b 1
)

set "HORA=%~1"
set "CADA=%~2"
set "HASTA=%~3"
if not "%HORA%"=="" goto crear

echo.
echo Programar la actualizacion automatica de Calidad A365
echo -----------------------------------------------------
echo Antes, abre CalidadA365.exe y usa "Solo publicar" una vez para dejar guardados
echo tu nombre y correo de Git y la sesion de GitHub.
echo.
set /p "HORA=Hora de la primera ejecucion del dia (HH:MM, ej. 08:30): "
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

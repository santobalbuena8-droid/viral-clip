@echo off
REM Arranca Viral Clip en 0.0.0.0:8741 (accesible desde el celular en la misma Wi-Fi).
setlocal
cd /d "%~dp0\.."

if "%MAX_DURATION_SEC%"=="" set MAX_DURATION_SEC=7200
if "%HOST%"=="" set HOST=0.0.0.0
if "%PORT%"=="" set PORT=8741

if exist ".venv\Scripts\uvicorn.exe" (
  set UV=.venv\Scripts\uvicorn.exe
) else (
  where uvicorn >nul 2>&1
  if errorlevel 1 (
    echo No encuentro uvicorn. Crea el venv e instala deps:
    echo   python -m venv .venv
    echo   .venv\Scripts\activate
    echo   pip install -r requirements.txt
    exit /b 1
  )
  set UV=uvicorn
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo AVISO: ffmpeg no esta en el PATH. Instalalo antes de crear clips.
)

echo Viral Clip en http://0.0.0.0:%PORT%
echo En el celular / Chrome usa http://TU_IP_LAN:%PORT%
echo MAX_DURATION_SEC=%MAX_DURATION_SEC%
"%UV%" app.main:app --host %HOST% --port %PORT%
endlocal

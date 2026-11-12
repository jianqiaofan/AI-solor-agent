@echo off
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "APP_DIR=%ROOT%\subsystems\extraction"
set "PYTHONW=D:\developTools\miniconda3-26\envs\ai-solor-agent\pythonw.exe"

if not exist "%PYTHONW%" (
  echo Cannot find %PYTHONW%
  pause
  exit /b 1
)

cd /d "%APP_DIR%"
start "" /D "%APP_DIR%" "%PYTHONW%" -m extraction ui

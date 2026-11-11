@echo off
set "APP_DIR=E:\cursor-demo\AI-solor-agent\subsystems\extraction"
set "PYTHONW=C:\Users\jianq\miniconda3\envs\ai-solor-agent\pythonw.exe"

if not exist "%PYTHONW%" (
  echo Cannot find %PYTHONW%
  pause
  exit /b 1
)

cd /d "%APP_DIR%"
start "" /D "%APP_DIR%" "%PYTHONW%" -m extraction ui

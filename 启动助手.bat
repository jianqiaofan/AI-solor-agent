@echo off
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "PYTHONW=D:\developTools\miniconda3-26\envs\ai-solor-agent\pythonw.exe"

if not exist "%PYTHONW%" (
  echo Cannot find %PYTHONW%
  pause
  exit /b 1
)

powershell -NoProfile -Command "Start-Process -FilePath $env:PYTHONW -ArgumentList '-m','agent' -WorkingDirectory $env:ROOT -WindowStyle Normal"

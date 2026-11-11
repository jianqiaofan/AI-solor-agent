@echo off
set "ROOT=E:\cursor-demo\AI-solor-agent"
set "PYTHONW=C:\Users\jianq\miniconda3\envs\ai-solor-agent\pythonw.exe"

if not exist "%PYTHONW%" (
  echo Cannot find %PYTHONW%
  pause
  exit /b 1
)

powershell -NoProfile -Command "Start-Process -FilePath $env:PYTHONW -ArgumentList '-m','agent' -WorkingDirectory $env:ROOT -WindowStyle Normal"

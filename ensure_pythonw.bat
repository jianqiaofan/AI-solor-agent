@echo off
rem Create pythonw.local.bat once. If it already exists, leave it unchanged.
if exist "%~dp0pythonw.local.bat" exit /b 0

setlocal EnableExtensions
set "FOUND="
call :try "%USERPROFILE%\miniconda3\envs\ai-solor-agent\pythonw.exe"
call :try "%USERPROFILE%\Miniconda3\envs\ai-solor-agent\pythonw.exe"
call :try "%USERPROFILE%\anaconda3\envs\ai-solor-agent\pythonw.exe"
call :try "%USERPROFILE%\Anaconda3\envs\ai-solor-agent\pythonw.exe"
call :try "%LOCALAPPDATA%\miniconda3\envs\ai-solor-agent\pythonw.exe"
call :try "D:\developTools\miniconda3-26\envs\ai-solor-agent\pythonw.exe"

for /f "delims=" %%C in ('where conda 2^>nul') do (
  if not defined FOUND call :from_conda "%%~dpC"
)

if not defined FOUND exit /b 1

> "%~dp0pythonw.local.bat" echo @echo off
>> "%~dp0pythonw.local.bat" echo set "PYTHONW=%FOUND%"
exit /b 0

:try
if defined FOUND exit /b 0
if exist "%~1" set "FOUND=%~1"
exit /b 0

:from_conda
if defined FOUND exit /b 0
call :try "%~dp1..\envs\ai-solor-agent\pythonw.exe"
call :try "%~dp1..\..\envs\ai-solor-agent\pythonw.exe"
exit /b 0

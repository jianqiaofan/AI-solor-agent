@echo off
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
call "%ROOT%\ensure_pythonw.bat"
if errorlevel 1 goto :missing
call "%ROOT%\pythonw.local.bat"
if not exist "%PYTHONW%" goto :missing

powershell -NoProfile -Command "Start-Process -FilePath $env:PYTHONW -ArgumentList '-m','agent' -WorkingDirectory $env:ROOT -WindowStyle Normal"
exit /b 0

:missing
echo Cannot find this computer's pythonw.exe.
echo Edit pythonw.local.bat next to this file and set PYTHONW.
echo That file stays on this computer and is not replaced by git pull.
pause
exit /b 1

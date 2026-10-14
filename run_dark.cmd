@echo off
setlocal
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" goto setup
if not exist "resource_rc.py" goto setup
if not exist "vendor\FluentUI\imports\resource_rc.py" goto setup
goto run
:setup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if errorlevel 1 goto failed
:run
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py" --theme dark
if errorlevel 1 goto failed
popd
exit /b 0
:failed
echo Unable to start Thrashing Mitigator. See the error above.
pause
popd
exit /b 1

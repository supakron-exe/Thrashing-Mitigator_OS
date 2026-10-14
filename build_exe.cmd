@echo off
setlocal
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.cmd first.
    popd
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" tools\build_exe.py
if errorlevel 1 goto failed
popd
exit /b 0
:failed
popd
exit /b 1

@echo off
setlocal
title AI Shopping Assistant - tests
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [!] No virtual environment found. Creating one and installing requirements...
    python -m venv .venv || goto :error
    call ".venv\Scripts\activate.bat"
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt || goto :error
)

call ".venv\Scripts\activate.bat"
echo Running the offline test suite (no network, no API key needed)...
echo.
python -m pytest -q
if %errorlevel% gtr 0 (echo WARNING: failures) else (echo PASSED)
goto :end

:error
echo [!] Setup failed. Read the messages above.

:end
pause
endlocal

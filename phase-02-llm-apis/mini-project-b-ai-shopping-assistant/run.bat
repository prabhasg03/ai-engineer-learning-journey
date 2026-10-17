@echo off
setlocal
title AI Shopping Assistant - server
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [!] No virtual environment found. Creating one and installing requirements...
    python -m venv .venv || goto :error
    call ".venv\Scripts\activate.bat"
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt || goto :error
)

call ".venv\Scripts\activate.bat"
echo.
echo Starting the AI Shopping Assistant...
echo   API docs (Swagger UI): http://127.0.0.1:8000/docs
echo   Health:                http://127.0.0.1:8000/health
echo   Press CTRL+C to stop.
echo.
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
goto :end

:error
echo [!] Setup failed. Read the messages above.

:end
pause
endlocal

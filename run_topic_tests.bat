@echo off
setlocal enabledelayedexpansion

rem Runs every Phase 2 topic test suite (fast, offline, no API keys needed).
rem Usage: double-click this file, or run it from a terminal.

set "ROOT=%~dp0phase-02-llm-apis"
set "FAIL=0"
set "RAN=0"

echo ============================================================
echo  Phase 2 - LLM APIs as a backend engineer : test sweep
echo ============================================================
echo.

for /d %%D in ("%ROOT%\topic-*") do (
    if exist "%%D\implementation\test_*.py" (
        echo ------------------------------------------------------------
        echo  %%~nxD
        echo ------------------------------------------------------------
        pushd "%%D\implementation"
        python -m pytest -q
        if errorlevel 1 set "FAIL=1"
        popd
        set /a RAN+=1
        echo.
    )
)

if exist "%ROOT%\mini-project-b-ai-shopping-assistant\tests\test_*.py" (
    echo ------------------------------------------------------------
    echo  mini-project-b-ai-shopping-assistant
    echo ------------------------------------------------------------
    pushd "%ROOT%\mini-project-b-ai-shopping-assistant"
    python -m pytest -q
    if errorlevel 1 set "FAIL=1"
    popd
    set /a RAN+=1
    echo.
)

echo ============================================================
if "%FAIL%"=="1" (
    echo  RESULT: FAILURES - see above
) else (
    echo  RESULT: all ^(!RAN!^) suites passed
)
echo ============================================================

endlocal
pause

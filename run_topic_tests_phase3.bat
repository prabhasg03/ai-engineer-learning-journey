@echo off
setlocal enabledelayedexpansion

rem Runs every Phase 3 topic test suite (fast, offline, no API keys needed).
rem Usage: double-click this file, or run it from a terminal.

set "ROOT=%~dp0phase-03-embeddings-rag"
set "FAIL=0"
set "RAN=0"

echo ============================================================
echo  Phase 3 - Embeddings and RAG : test sweep
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

echo ============================================================
if "%FAIL%"=="1" (
    echo  RESULT: FAILURES - see above
) else (
    echo  RESULT: all ^(!RAN!^) suites passed
)
echo ============================================================

endlocal
pause

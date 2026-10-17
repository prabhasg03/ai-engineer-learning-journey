@echo off
setlocal

echo Running Topic 17 pytest suite...
echo.
echo [1] Topic 17: Tool calling
cd /d "E:\ai-engineering-learning\phase-02-llm-apis\topic-17-tool-calling\implementation"

python -m pytest -v 2>&1

if %errorlevel% gtr 0 (
    echo.
    echo WARNING: Topic 17 tests had failures
) else (
    echo.
    echo Topic 17 tests: PASSED
)

echo.
echo Topic 17 tests completed.
endlocal
pause

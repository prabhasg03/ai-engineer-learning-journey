@echo off
setlocal

echo Running Topic 19a pytest suite (fallbacks / failover)...
cd /d "E:\ai-engineering-learning\phase-02-llm-apis\topic-19a-fallbacks-failover\implementation"

python -m pytest -v 2>&1

if %errorlevel% gtr 0 (
    echo.
    echo WARNING: Topic 19a tests had failures
) else (
    echo.
    echo Topic 19a tests: PASSED
)

echo.
echo Topic 19a tests completed.
endlocal
pause

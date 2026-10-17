@echo off
setlocal

echo Running Topic 20 pytest suite...
echo.
echo [1] Topic 20: reasoning models and test-time compute
cd /d "E:\ai-engineering-learning\phase-02-llm-apis\topic-20-reasoning-models\implementation"

python -m pytest -v 2>&1

if %errorlevel% gtr 0 (
    echo.
    echo WARNING: Topic 20 tests had failures
) else (
    echo.
    echo Topic 20 tests: PASSED
)

echo.
echo Topic 20 tests completed.
pause
endlocal

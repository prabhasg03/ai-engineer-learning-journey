@echo off
setlocal

echo Running Topic 16 pytest suite...
echo.
echo [1] Topic 16: FastAPI essentials
cd /d "E:\ai-engineering-learning\phase-02-llm-apis\topic-16-fastapi-essentials\implementation"

python -m pytest -v 2>&1

if %errorlevel% gtr 0 (
    echo.
    echo WARNING: Topic 16 tests had failures
) else (
    echo.
    echo Topic 16 tests: PASSED
)

echo.
echo Topic 16 tests completed.
endlocal
pause

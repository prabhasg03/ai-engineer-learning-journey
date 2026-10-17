@echo off
setlocal

echo Running Topic 19c pytest suite (model routing)...
cd /d "E:\ai-engineering-learning\phase-02-llm-apis\topic-19c-model-routing\implementation"

python -m pytest -v 2>&1

if %errorlevel% gtr 0 (
    echo.
    echo WARNING: Topic 19c tests had failures
) else (
    echo.
    echo Topic 19c tests: PASSED
)

echo.
echo Topic 19c tests completed.
endlocal
pause

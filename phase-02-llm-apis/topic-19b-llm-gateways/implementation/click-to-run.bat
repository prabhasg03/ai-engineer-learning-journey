@echo off
setlocal

echo Running Topic 19b pytest suite (LLM gateways)...
cd /d "E:\ai-engineering-learning\phase-02-llm-apis\topic-19b-llm-gateways\implementation"

python -m pytest -v 2>&1

if %errorlevel% gtr 0 (
    echo.
    echo WARNING: Topic 19b tests had failures
) else (
    echo.
    echo Topic 19b tests: PASSED
)

echo.
echo Topic 19b tests completed.
endlocal
pause

@echo off
setlocal

echo Running Topic 21 pytest suite...
echo.
echo [1] Topic 21: decision - when NOT to use an LLM
cd /d "E:\ai-engineering-learning\phase-02-llm-apis\topic-21-when-not-to-use-llm\implementation"

python -m pytest -v 2>&1

if %errorlevel% gtr 0 (
    echo.
    echo WARNING: Topic 21 tests had failures
) else (
    echo.
    echo Topic 21 tests: PASSED
)

echo.
echo Topic 21 tests completed.
pause
endlocal

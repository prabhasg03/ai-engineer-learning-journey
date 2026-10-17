@echo off
setlocal

echo Running Topic 19 pytest suite...
echo.
echo [1] Topic 19: Failure handling (retries, backoff + jitter, Retry-After)
cd /d "E:\ai-engineering-learning\phase-02-llm-apis\topic-19-failure-handling\implementation"

python -m pytest -v 2>&1

if %errorlevel% gtr 0 (
    echo.
    echo WARNING: Topic 19 tests had failures
) else (
    echo.
    echo Topic 19 tests: PASSED
)

echo.
echo Topic 19 tests completed.
endlocal
pause

@echo off
setlocal

echo Running Topic 26 pytest suite...
echo.
echo [1] Topic 26: the retrieval pipeline end to end
cd /d "E:\ai-engineering-learning\phase-03-embeddings-rag\topic-26-retrieval-pipeline\implementation"

python -m pytest -v 2>&1

if %errorlevel% gtr 0 (
    echo.
    echo WARNING: Topic 26 tests had failures
) else (
    echo.
    echo Topic 26 tests: PASSED
)

echo.
echo Topic 26 tests completed.
endlocal
pause

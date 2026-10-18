@echo off
setlocal

echo Running Topic 24 pytest suite...
echo.
echo [1] Topic 24: Chunking
cd /d "E:\ai-engineering-learning\phase-03-embeddings-rag\topic-24-chunking\implementation"

python -m pytest -v 2>&1

if %errorlevel% gtr 0 (
    echo.
    echo WARNING: Topic 24 tests had failures
) else (
    echo.
    echo Topic 24 tests: PASSED
)

echo.
echo Topic 24 tests completed.
endlocal
pause

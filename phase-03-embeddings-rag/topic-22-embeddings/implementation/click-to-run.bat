@echo off
setlocal

echo Running Topic 22 pytest suite...
echo.
echo [1] Topic 22: Embeddings
cd /d "E:\ai-engineering-learning\phase-03-embeddings-rag\topic-22-embeddings\implementation"

python -m pytest -v 2>&1

if %errorlevel% gtr 0 (
    echo.
    echo WARNING: Topic 22 tests had failures
) else (
    echo.
    echo Topic 22 tests: PASSED
)

echo.
echo Topic 22 tests completed.
endlocal
pause

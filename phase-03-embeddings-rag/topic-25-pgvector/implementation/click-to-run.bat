@echo off
setlocal

echo Running Topic 25 pytest suite...
echo.
echo [1] Topic 25: pgvector
cd /d "E:\ai-engineering-learning\phase-03-embeddings-rag\topic-25-pgvector\implementation"

python -m pytest -v 2>&1

if %errorlevel% gtr 0 (
    echo.
    echo WARNING: Topic 25 tests had failures
) else (
    echo.
    echo Topic 25 tests: PASSED
)

echo.
echo Topic 25 tests completed.
endlocal
pause

@echo off
setlocal

echo Running Topic 28 pytest suite...
echo.
echo [1] Topic 28: where RAG fails
cd /d "E:\ai-engineering-learning\phase-03-embeddings-rag\topic-28-where-rag-fails\implementation"

python -m pytest -v 2>&1

if %errorlevel% gtr 0 (
    echo.
    echo WARNING: Topic 28 tests had failures
) else (
    echo.
    echo Topic 28 tests: PASSED
)

echo.
echo Topic 28 tests completed.
endlocal
pause

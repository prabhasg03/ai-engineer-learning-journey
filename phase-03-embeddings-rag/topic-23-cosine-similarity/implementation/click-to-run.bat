@echo off
setlocal

echo Running Topic 23 pytest suite...
echo.
echo [1] Topic 23: Cosine similarity
cd /d "E:\ai-engineering-learning\phase-03-embeddings-rag\topic-23-cosine-similarity\implementation"

python -m pytest -v 2>&1

if %errorlevel% gtr 0 (
    echo.
    echo WARNING: Topic 23 tests had failures
) else (
    echo.
    echo Topic 23 tests: PASSED
)

echo.
echo Topic 23 tests completed.
endlocal
pause

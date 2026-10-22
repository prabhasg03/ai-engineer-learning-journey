@echo off
setlocal

echo Running Topic 27 pytest suite...
echo.
echo [1] Topic 27: prompt construction from retrieved context
cd /d "E:\ai-engineering-learning\phase-03-embeddings-rag\topic-27-prompt-construction\implementation"

python -m pytest -v 2>&1

if %errorlevel% gtr 0 (
    echo.
    echo WARNING: Topic 27 tests had failures
) else (
    echo.
    echo Topic 27 tests: PASSED
)

echo.
echo Topic 27 tests completed.
endlocal
pause

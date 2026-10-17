@echo off
setlocal

echo Running Topic 18 pytest suite...
echo.
echo [1] Topic 18: MCP server/client (tools/resources/prompts) + transports + OAuth 2.1 + security
cd /d "E:\ai-engineering-learning\phase-02-llm-apis\topic-18-mcp-oauth-security\implementation"

python -m pytest -v 2>&1

if %errorlevel% gtr 0 (
    echo.
    echo WARNING: Topic 18 tests had failures
) else (
    echo.
    echo Topic 18 tests: PASSED
)

echo.
echo Topic 18 tests completed.
endlocal
pause

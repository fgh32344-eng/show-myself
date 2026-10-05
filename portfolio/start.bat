@echo off
rem ============================================================
rem  Wang Yaowei - Personal Portfolio  launcher
rem
rem  IMPORTANT - keep this file ASCII-only and saved as CP936.
rem  cmd.exe parses .bat byte by byte using the system ANSI code
rem  page. Chinese text in a .bat file is easily corrupted into
rem  mojibake, and mojibake bytes can be treated as command
rem  separators, which shreds set/if/goto lines.
rem
rem  The Chinese startup banner is therefore printed by Python
rem  (backend/app.py), which handles console encoding itself.
rem  Do NOT add "chcp 65001" here: it conflicts with the CP936
rem  file content and turns the banner into double-encoded text.
rem ============================================================
setlocal enableextensions

set "SCRIPT_DIR=%~dp0"
set "PYTHON="

rem ---- 0. active conda/venv environment ----
rem If a virtual environment is activated, prefer it: a user who installed
rem fastapi into that environment expects it to be used. Without this step
rem the py launcher below would win and silently fall back to the
rem zero-dependency server, hiding the fact that fastapi is available.
if defined CONDA_PREFIX (
  if exist "%CONDA_PREFIX%\python.exe" set "PYTHON=%CONDA_PREFIX%\python.exe"
)
if not defined PYTHON (
  if defined VIRTUAL_ENV (
    if exist "%VIRTUAL_ENV%\Scripts\python.exe" set "PYTHON=%VIRTUAL_ENV%\Scripts\python.exe"
  )
)
if not defined PYTHON (
  if defined PORTFOLIO_PYTHON (
    if exist "%PORTFOLIO_PYTHON%" set "PYTHON=%PORTFOLIO_PYTHON%"
  )
)

rem ---- 1. system py launcher ----
if not defined PYTHON (
  where py >nul 2>nul
  if not errorlevel 1 set "PYTHON=py"
)

rem ---- 2. python on PATH ----
if not defined PYTHON (
  where python >nul 2>nul
  if not errorlevel 1 set "PYTHON=python"
)

rem ---- 3. bundled DSH python runtime ----
if not defined PYTHON (
  set "BUNDLED=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
  if exist "%BUNDLED%" set "PYTHON=%BUNDLED%"
)

if not defined PYTHON (
  echo.
  echo   [ERROR] Python not found. Please install Python 3.10+ :
  echo   https://www.python.org/downloads/
  echo.
  pause
  exit /b 1
)

rem ---- defaults (override by setting these before launch) ----
if "%PORTFOLIO_HOST%"=="" set "PORTFOLIO_HOST=127.0.0.1"
if "%PORTFOLIO_PORT%"=="" set "PORTFOLIO_PORT=8000"

rem Report which interpreter is used, and whether FastAPI is available,
rem so a silent fallback cannot go unnoticed.
"%PYTHON%" -c "import fastapi" >nul 2>nul
if errorlevel 1 (
  set "MODE=zero-dependency stdlib (fastapi not found)"
) else (
  set "MODE=FastAPI + uvicorn"
)
echo.
echo   Python : %PYTHON%
echo   Mode   : %MODE%
if not "%MODE%"=="FastAPI + uvicorn" (
  echo   Tip    : pip install -r "%SCRIPT_DIR%backend\requirements.txt"
)

rem app.py picks FastAPI when available and otherwise falls back
rem to the zero-dependency standard library server.
"%PYTHON%" "%SCRIPT_DIR%backend\app.py"
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
  echo.
  echo   Server exited with code %EXITCODE%.
  echo   If a module is missing, run:
  echo     pip install -r "%SCRIPT_DIR%backend\requirements.txt"
  echo   Or use the zero-dependency mode directly:
  echo     python "%SCRIPT_DIR%backend\server.py"
  echo.
  pause
)

endlocal

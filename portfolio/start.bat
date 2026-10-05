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

rem ============================================================
rem  Interpreter selection - first match wins:
rem    0a. PORTFOLIO_PYTHON              explicit override, highest priority
rem    0b. activated conda / venv        the environment you are working in
rem    0c. CONDA_ENVS_DIRS\person        this project's designated environment
rem    1.  py launcher
rem    2.  python on PATH
rem    3.  bundled DSH runtime
rem
rem  Changing 0c: edit PORTFOLIO_ENV_NAME below, or set PORTFOLIO_PYTHON.
rem  Changing the conda root: set PORTFOLIO_CONDA_ROOT before launching.
rem ============================================================

rem ---- 0c target environment (must match your conda env name) ----
if not defined PORTFOLIO_ENV_NAME set "PORTFOLIO_ENV_NAME=person"
if not defined PORTFOLIO_CONDA_ROOT (
  if exist "D:\conda\envs" (
    set "PORTFOLIO_CONDA_ROOT=D:\conda"
  ) else if exist "%USERPROFILE%\miniconda3\envs" (
    set "PORTFOLIO_CONDA_ROOT=%USERPROFILE%\miniconda3"
  ) else if exist "%USERPROFILE%\anaconda3\envs" (
    set "PORTFOLIO_CONDA_ROOT=%USERPROFILE%\anaconda3"
  )
)

rem ---- 0a. explicit override (highest priority) ----
if defined PORTFOLIO_PYTHON (
  if exist "%PORTFOLIO_PYTHON%" set "PYTHON=%PORTFOLIO_PYTHON%"
)

rem ---- 0b. already activated conda/venv environment ----
if not defined PYTHON (
  if defined CONDA_PREFIX (
    if exist "%CONDA_PREFIX%\python.exe" set "PYTHON=%CONDA_PREFIX%\python.exe"
  )
)
if not defined PYTHON (
  if defined VIRTUAL_ENV (
    if exist "%VIRTUAL_ENV%\Scripts\python.exe" set "PYTHON=%VIRTUAL_ENV%\Scripts\python.exe"
  )
)

rem ---- 0c. this project's designated conda environment ----
if not defined PYTHON (
  if defined PORTFOLIO_CONDA_ROOT (
    if exist "%PORTFOLIO_CONDA_ROOT%\envs\%PORTFOLIO_ENV_NAME%\python.exe" (
      set "PYTHON=%PORTFOLIO_CONDA_ROOT%\envs\%PORTFOLIO_ENV_NAME%\python.exe"
    )
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

rem ---- port pre-check ----
rem On Windows, binding an already-used port raises WinError 10013 and dumps a
rem Python traceback, which tells a user nothing. Detect it first and print
rem something actionable.
rem
rem The probe code goes through an environment variable instead of an inline
rem -c "..." argument: cmd.exe cannot handle nested double quotes inside a
rem for /f command and silently yields an empty result.
set "PORT_PROBE=import os,socket,sys;s=socket.socket();s.settimeout(1.5);sys.exit(0 if s.connect_ex((os.environ['PORTFOLIO_HOST'],int(os.environ['PORTFOLIO_PORT'])))==0 else 1)"
set "PORTOCCUPIED="
"%PYTHON%" -c "%PORT_PROBE%" >nul 2>nul
if not errorlevel 1 set "PORTOCCUPIED=1"

if defined PORTOCCUPIED (
  echo.
  echo   [ERROR] Port %PORTFOLIO_PORT% is already in use.
  echo   Another instance is probably still running. To fix it, either:
  echo.
  echo     1^) Stop the process holding the port ^(PowerShell^):
  echo        Get-NetTCPConnection -LocalPort %PORTFOLIO_PORT% -State Listen ^|
  echo          ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
  echo.
  echo     2^) Or start this one on another port:
  echo        set PORTFOLIO_PORT=8001 ^&^& start.bat
  echo.
  pause
  exit /b 1
)

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
echo   Port   : %PORTFOLIO_HOST%:%PORTFOLIO_PORT%
echo   Mode   : %MODE%
if not "%MODE%"=="FastAPI + uvicorn" (
  echo   Tip    : activate a conda/venv that has fastapi, or set PORTFOLIO_PYTHON
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

@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set "ROOT=%~dp0"
set "FRONTEND_DIR=%ROOT%frontend"
set "BACKEND_DIR=%ROOT%backend"
set "VENV_DIR=%BACKEND_DIR%\.venv"

echo ============================================
echo   Pixpress1 - AI Photo Album Layout System
echo ============================================
echo.

REM ---- Check prerequisites ----
where node >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Node.js not found. Please install Node.js first.
  exit /b 1
)

where py >nul 2>&1
if errorlevel 1 (
  where python >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.11+ first.
    exit /b 1
  )
)

echo [INFO] Node.js and Python are ready.
echo.

REM ---- Install frontend dependencies ----
if not exist "%FRONTEND_DIR%\node_modules" (
  echo [1/5] Installing frontend dependencies...
  pushd "%FRONTEND_DIR%"
  call npm install
  if errorlevel 1 (
    echo [ERROR] Frontend dependency installation failed.
    popd
    exit /b 1
  )
  popd
  echo [ OK ] Frontend dependencies installed.
) else (
  echo [1/5] Frontend dependencies already installed, skipping.
)

REM ---- Setup frontend .env ----
if not exist "%FRONTEND_DIR%\.env" (
  if exist "%FRONTEND_DIR%\.env.example" (
    copy "%FRONTEND_DIR%\.env.example" "%FRONTEND_DIR%\.env" >nul
    echo [ OK ] Frontend .env created from .env.example.
  )
)

REM ---- Setup backend .env ----
if not exist "%BACKEND_DIR%\.env" (
  if exist "%BACKEND_DIR%\.env.example" (
    copy "%BACKEND_DIR%\.env.example" "%BACKEND_DIR%\.env" >nul
    echo [ OK ] Backend .env created from .env.example.
  )
)

REM ---- Create backend virtual environment ----
if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo [2/5] Creating backend virtual environment...
  py -3 -m venv "%VENV_DIR%" 2>nul
  if errorlevel 1 (
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
      echo [ERROR] Python virtual environment creation failed.
      exit /b 1
    )
  )
  echo [ OK ] Virtual environment created.
) else (
  echo [2/5] Virtual environment already exists, skipping.
)

REM ---- Install backend dependencies ----
if not exist "%VENV_DIR%\.deps_ready" (
  echo [3/5] Installing backend dependencies...
  call "%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip -q
  call "%VENV_DIR%\Scripts\python.exe" -m pip install -r "%BACKEND_DIR%\requirements.txt" -q
  if errorlevel 1 (
    echo [ERROR] Backend dependency installation failed.
    exit /b 1
  )
  type nul > "%VENV_DIR%\.deps_ready"
  echo [ OK ] Backend dependencies installed.
) else (
  echo [3/5] Backend dependencies already installed, skipping.
)

REM ---- Check external services ----
echo [4/5] Checking external services...
echo   - PostgreSQL : localhost:5432 (make sure it is running)
echo   - Redis      : localhost:6379 (make sure it is running)
echo   - MinIO      : localhost:9000 (optional, local filesystem used)
echo.

REM ---- Start services ----
echo [5/5] Starting services...
echo.
echo   Backend  API : http://127.0.0.1:8000
echo   Backend Docs : http://127.0.0.1:8000/docs
echo   Frontend App : http://127.0.0.1:5173
echo ============================================

start "Pixpress1 Backend" cmd /k "cd /d "%BACKEND_DIR%" && call ".venv\Scripts\activate.bat" && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
start "Pixpress1 Frontend" cmd /k "cd /d "%FRONTEND_DIR%" && npm run dev -- --host 127.0.0.1 --port 5173"

echo.
echo Services started. Check the two new terminal windows.
echo Close a terminal window to stop the corresponding service.
exit /b 0

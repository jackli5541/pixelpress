@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion

set "ROOT=%~dp0"
set "COMPOSE_FILE=%ROOT%compose.prod.yml"
set "TEST_COMPOSE_FILE=%ROOT%compose.test.yml"
set "BACKEND_ENV_FILE=%ROOT%backend\.env"
set "COMMAND=%~1"
set "START_LOG_DIR=%ROOT%.tmp_start"
set "START_LOG_FILE=%START_LOG_DIR%\start.last.log"
set "COMPOSE_ENV_FILE=%START_LOG_DIR%\compose.runtime.env"
set "INTERACTIVE_LAUNCH=0"
if "%COMMAND%"=="" set "INTERACTIVE_LAUNCH=1"
if not exist "%START_LOG_DIR%" mkdir "%START_LOG_DIR%" >nul 2>&1
type nul > "%START_LOG_FILE%"

for %%F in ("%BACKEND_ENV_FILE%") do if exist %%~fF (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%%~fF") do (
    if not "%%~A"=="" (
      if /I not "%%~A"=="REM" if not defined %%~A set "%%~A=%%~B"
    )
  )
)

if not defined PYTHON_BASE_IMAGE set "PYTHON_BASE_IMAGE=docker.m.daocloud.io/library/python:3.11-slim"
if not defined NODE_BASE_IMAGE set "NODE_BASE_IMAGE=docker.m.daocloud.io/library/node:20-alpine"
if not defined NGINX_BASE_IMAGE set "NGINX_BASE_IMAGE=docker.m.daocloud.io/library/nginx:1.27-alpine"
if not defined PIP_INDEX_URL set "PIP_INDEX_URL=https://pypi.org/simple"
if not defined APT_MIRROR_HOST set "APT_MIRROR_HOST=deb.debian.org"
if not defined NPM_REGISTRY_URL set "NPM_REGISTRY_URL=https://registry.npmmirror.com"
if not defined PLAYWRIGHT_DOWNLOAD_HOST set "PLAYWRIGHT_DOWNLOAD_HOST=https://registry.npmmirror.com/-/binary/playwright"
if not defined PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD set "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0"
if not defined MINIO_ACCESS_KEY set "MINIO_ACCESS_KEY=minioadmin"
if not defined MINIO_SECRET_KEY set "MINIO_SECRET_KEY=minioadmin"
if not defined MINIO_BUCKET set "MINIO_BUCKET=pixpress1"
if not defined POSTGRES_PASSWORD set "POSTGRES_PASSWORD=postgres"
if not defined OBSERVABILITY_LOG_LEVEL set "OBSERVABILITY_LOG_LEVEL=INFO"
if not defined OBSERVABILITY_JSON_LOGS set "OBSERVABILITY_JSON_LOGS=true"
if not defined CORS_ALLOW_ORIGINS set "CORS_ALLOW_ORIGINS=["http://127.0.0.1","http://localhost"]"

if not defined AUTH_SECRET_KEY set "AUTH_SECRET_KEY=pixpress1-prod-auth-key-2026-1234"
if /I "%AUTH_SECRET_KEY%"=="change-me-in-production" set "AUTH_SECRET_KEY=pixpress1-prod-auth-key-2026-1234"
if "%AUTH_SECRET_KEY:~31,1%"=="" (
  echo [ERROR] AUTH_SECRET_KEY must be at least 32 characters.
  exit /b 1
)

if not defined SECRETS_MASTER_KEY set "SECRETS_MASTER_KEY=pixpress1-secrets-master-key-2026-abcdef"
if /I "%SECRETS_MASTER_KEY%"=="change-me-too" set "SECRETS_MASTER_KEY=pixpress1-secrets-master-key-2026-abcdef"
if "%SECRETS_MASTER_KEY:~31,1%"=="" (
  echo [ERROR] SECRETS_MASTER_KEY must be at least 32 characters.
  exit /b 1
)

if /I "%AUTH_SECRET_KEY%"=="%SECRETS_MASTER_KEY%" (
  echo [ERROR] AUTH_SECRET_KEY and SECRETS_MASTER_KEY must be different.
  exit /b 1
)

if /I "%COMMAND%"=="down" goto down
if /I "%COMMAND%"=="logs" goto logs
if /I "%COMMAND%"=="ps" goto ps
if /I "%COMMAND%"=="restart" goto restart
if /I "%COMMAND%"=="test" goto test
if /I "%COMMAND%"=="test-render" goto test_render
if /I "%COMMAND%"=="test-up" goto test_up
if /I "%COMMAND%"=="test-down" goto test_down
if /I "%COMMAND%"=="test-logs" goto test_logs
if /I "%COMMAND%"=="test-ps" goto test_ps
if /I "%COMMAND%"=="pull" goto pull
if /I "%COMMAND%"=="help" goto help

call :check_docker || goto fail
call :up || goto fail
if "%INTERACTIVE_LAUNCH%"=="1" goto success_pause
exit /b 0

:check_docker
echo ============================================
echo   Pixpress1 - Container Delivery Launcher
echo ============================================
echo.
echo [Env] backend\.env=%BACKEND_ENV_FILE%
echo [Env] compose env=%COMPOSE_ENV_FILE%
echo [Mirror] PYTHON_BASE_IMAGE=%PYTHON_BASE_IMAGE%
echo [Mirror] NODE_BASE_IMAGE=%NODE_BASE_IMAGE%
echo [Mirror] NGINX_BASE_IMAGE=%NGINX_BASE_IMAGE%
echo [Mirror] PIP_INDEX_URL=%PIP_INDEX_URL%
echo [Mirror] NPM_REGISTRY_URL=%NPM_REGISTRY_URL%
echo [Config] AUTH_SECRET_KEY length OK
echo [Config] SECRETS_MASTER_KEY length OK
echo [Config] CORS_ALLOW_ORIGINS=%CORS_ALLOW_ORIGINS%
echo.

docker version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker is not available. Please start Docker Desktop first.
  exit /b 1
)

docker compose version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] docker compose is not available. Please install a Docker version with Compose support.
  exit /b 1
)

if not exist "%COMPOSE_FILE%" (
  echo [ERROR] compose.prod.yml was not found: %COMPOSE_FILE%
  exit /b 1
)

if not exist "%TEST_COMPOSE_FILE%" (
  echo [ERROR] compose.test.yml was not found: %TEST_COMPOSE_FILE%
  exit /b 1
)

call :write_compose_env || exit /b 1

exit /b 0

:write_compose_env
powershell -NoProfile -Command ^
  "$content = @();" ^
  "$content += 'AUTH_SECRET_KEY=' + $env:AUTH_SECRET_KEY;" ^
  "$content += 'SECRETS_MASTER_KEY=' + $env:SECRETS_MASTER_KEY;" ^
  "$content += 'CORS_ALLOW_ORIGINS=' + $env:CORS_ALLOW_ORIGINS;" ^
  "Set-Content -Path $env:COMPOSE_ENV_FILE -Value $content -Encoding ascii"
if errorlevel 1 (
  echo [ERROR] Failed to write Docker compose env file: %COMPOSE_ENV_FILE%
  exit /b 1
)
exit /b 0

:up
echo [1/3] Rebuilding images from the latest code and starting the production-style container stack...
pushd "%ROOT%"
docker compose --env-file "%COMPOSE_ENV_FILE%" -f "%COMPOSE_FILE%" up -d --build
if errorlevel 1 (
  echo [ERROR] Failed to rebuild/start compose.prod.yml.
  popd
  exit /b 1
)

echo.
echo [2/3] Current service status:
docker compose --env-file "%COMPOSE_ENV_FILE%" -f "%COMPOSE_FILE%" ps
if errorlevel 1 (
  echo [ERROR] Failed to read container status.
  popd
  exit /b 1
)

echo.
echo [3/3] Startup request completed.
echo.
echo   Frontend App : http://127.0.0.1/
echo   Backend API  : http://127.0.0.1/api/v1
echo   API Health   : http://127.0.0.1/api/v1/health
echo   API Docs     : http://127.0.0.1/docs
echo.
echo Helpful commands:
echo   start.bat pull
echo   start.bat ps
echo   start.bat logs
echo   start.bat down
echo   start.bat test
echo   start.bat test-up
echo   start.bat test-down
popd
exit /b 0

:down
call :check_docker || exit /b 1
pushd "%ROOT%"
docker compose --env-file "%COMPOSE_ENV_FILE%" -f "%COMPOSE_FILE%" down
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

:logs
call :check_docker || exit /b 1
pushd "%ROOT%"
docker compose --env-file "%COMPOSE_ENV_FILE%" -f "%COMPOSE_FILE%" logs -f
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

:ps
call :check_docker || exit /b 1
pushd "%ROOT%"
docker compose --env-file "%COMPOSE_ENV_FILE%" -f "%COMPOSE_FILE%" ps
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

:restart
call :check_docker || exit /b 1
pushd "%ROOT%"
docker compose --env-file "%COMPOSE_ENV_FILE%" -f "%COMPOSE_FILE%" down
if errorlevel 1 (
  set "EXIT_CODE=%ERRORLEVEL%"
  popd
  exit /b %EXIT_CODE%
)
docker compose --env-file "%COMPOSE_ENV_FILE%" -f "%COMPOSE_FILE%" up -d --build
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

:pull
call :check_docker || exit /b 1
pushd "%ROOT%"
echo Pulling production images...
docker compose --env-file "%COMPOSE_ENV_FILE%" -f "%COMPOSE_FILE%" pull
if errorlevel 1 (
  set "EXIT_CODE=%ERRORLEVEL%"
  popd
  exit /b %EXIT_CODE%
)
echo.
echo Pulling test images...
docker compose --env-file "%COMPOSE_ENV_FILE%" -f "%TEST_COMPOSE_FILE%" pull
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

:test
echo Running backend integration tests in Docker...
call :check_docker || exit /b 1
pushd "%ROOT%"
docker compose --env-file "%COMPOSE_ENV_FILE%" -f "%TEST_COMPOSE_FILE%" up --build --abort-on-container-exit --exit-code-from backend-test
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

:test_render
echo Running targeted render and artifact tests in Docker...
call :check_docker || exit /b 1
pushd "%ROOT%"
docker compose --env-file "%COMPOSE_ENV_FILE%" -f "%TEST_COMPOSE_FILE%" run --rm backend-test pytest tests/integration/test_async_task_flow.py tests/integration/test_render_artifact_invalidation.py tests/integration/test_render_artifact_cleanup.py tests/integration/test_legacy_api_contract.py tests/integration/test_preview_render_assets.py tests/integration/test_page_preview_snippet.py -q
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

:test_up
call :check_docker || exit /b 1
pushd "%ROOT%"
docker compose --env-file "%COMPOSE_ENV_FILE%" -f "%TEST_COMPOSE_FILE%" up -d --build postgres-test redis-test
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

:test_down
call :check_docker || exit /b 1
pushd "%ROOT%"
docker compose --env-file "%COMPOSE_ENV_FILE%" -f "%TEST_COMPOSE_FILE%" down -v
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

:test_logs
call :check_docker || exit /b 1
pushd "%ROOT%"
docker compose --env-file "%COMPOSE_ENV_FILE%" -f "%TEST_COMPOSE_FILE%" logs -f backend-test postgres-test redis-test
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

:test_ps
call :check_docker || exit /b 1
pushd "%ROOT%"
docker compose --env-file "%COMPOSE_ENV_FILE%" -f "%TEST_COMPOSE_FILE%" ps
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%

:help
echo Usage:
echo   start.bat           Rebuild from latest code and start the production stack
echo   start.bat pull      Pull production and test images
echo   start.bat ps        Show production service status
echo   start.bat logs      Tail production compose logs
echo   start.bat down      Stop the production stack
echo   start.bat restart   Rebuild and restart the production stack (same as default start)
echo   start.bat test      Build and run backend integration tests in Docker
echo   start.bat test-render Run targeted render/artifact tests in Docker
echo   start.bat test-up   Start Docker test dependencies
echo   start.bat test-ps   Show Docker test service status
echo   start.bat test-logs Tail Docker test service logs
echo   start.bat test-down Stop and remove Docker test services and volumes
echo.
echo Runtime behavior:
echo   - Reuses backend\.env automatically when present
echo   - Auto-fills safe local AUTH_SECRET_KEY / SECRETS_MASTER_KEY if placeholders are found
echo   - Rebuilds backend/frontend images from the latest local code on each default start
echo   - Writes startup-only secrets and CORS settings to .tmp_start\compose.runtime.env for Docker Compose
echo   - Reuses existing postgres/redis/minio containers and data
echo   - Speeds up backend/worker/web builds via mirrored base images and package registries
echo   - Prepares startup runtime files in .tmp_start for Docker Compose
exit /b 0

:success_pause
echo.
echo [OK] start.bat completed.
pause
exit /b 0

:fail
echo.
echo [ERROR] start.bat failed.
pause
exit /b 1

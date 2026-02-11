@echo off
setlocal EnableDelayedExpansion

set "DISTRO=%~1"
set "WSL_TARGET="
set "DISTRO_LABEL=default"
set "BRIDGE_SERVICE=wslg-pulse-bridge.service"
set "FAIL=0"

if not "%DISTRO%"=="" (
    set "WSL_TARGET=-d %DISTRO%"
    set "DISTRO_LABEL=%DISTRO%"
)

echo [1/4] Stopping Docker compose stack and removing leftovers...
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker daemon is not running. Skipping compose cleanup.
) else (
    docker compose down --remove-orphans --volumes
    if errorlevel 1 (
        echo WARN: Compose cleanup reported errors.
        set "FAIL=1"
    )
)

echo [2/4] Stopping WSL pulse bridge service and stale bridge processes...
wsl %WSL_TARGET% -u root -- bash -lc "systemctl stop %BRIDGE_SERVICE% >/dev/null 2>&1 || true; systemctl kill %BRIDGE_SERVICE% >/dev/null 2>&1 || true; systemctl disable %BRIDGE_SERVICE% >/dev/null 2>&1 || true; systemctl reset-failed %BRIDGE_SERVICE% >/dev/null 2>&1 || true"
if errorlevel 1 (
    echo WARN: WSL bridge cleanup reported errors for distro "%DISTRO_LABEL%".
    set "FAIL=1"
)

echo [3/4] Verifying no monitor containers are left running...
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker daemon is not running. Container verification skipped.
) else (
    docker compose ps
)

echo [4/4] Verifying WSL bridge service state...
wsl %WSL_TARGET% -- bash -lc "systemctl is-active %BRIDGE_SERVICE% 2>/dev/null || true"

echo.
if "%FAIL%"=="1" (
    echo Cleanup completed with warnings.
    echo Review messages above and rerun if needed.
    exit /b 1
)

echo All monitoring-related services are stopped and cleaned.
echo Manual-only policy active: pulse bridge service is disabled.
exit /b 0

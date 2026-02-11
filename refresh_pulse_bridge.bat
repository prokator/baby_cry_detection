@echo off
setlocal EnableDelayedExpansion

set "DISTRO=%~1"
set "WSL_TARGET="
set "DISTRO_LABEL=default"
if not "%DISTRO%"=="" (
    set "WSL_TARGET=-d %DISTRO%"
    set "DISTRO_LABEL=%DISTRO%"
)

echo [1/4] Resolving WSL IP for distro "%DISTRO_LABEL%"...
set "WSL_IP="
for /f "usebackq delims=" %%i in (`wsl %WSL_TARGET% -- bash -lc "hostname -I | awk '{print $1}'"`) do (
    if not defined WSL_IP set "WSL_IP=%%i"
)

if not defined WSL_IP (
    echo ERROR: Could not resolve WSL IP. Ensure WSL default distro is running or pass distro name explicitly.
    echo Available distros:
    wsl -l -q
    exit /b 1
)
set "WSL_IP=%WSL_IP: =%"
echo WSL IP: %WSL_IP%

echo [2/4] Ensuring WSL pulse bridge service...
set "SERVICE_TMP=%TEMP%\wslg-pulse-bridge.service"
(
    echo [Unit]
    echo Description=Bridge WSLg Pulse socket to TCP 4713
    echo After=network.target
    echo.
    echo [Service]
    echo Type=simple
    echo ExecStart=/usr/bin/socat TCP-LISTEN:4713,fork,reuseaddr UNIX-CONNECT:/mnt/wslg/PulseServer
    echo Restart=always
    echo RestartSec=2
    echo.
    echo [Install]
    echo WantedBy=multi-user.target
) > "%SERVICE_TMP%"

wsl %WSL_TARGET% -u root -- sh -c "cat > /etc/systemd/system/wslg-pulse-bridge.service" < "%SERVICE_TMP%"
wsl %WSL_TARGET% -u root -- bash -lc "systemctl daemon-reload && systemctl enable --now wslg-pulse-bridge.service"
del /q "%SERVICE_TMP%" >nul 2>&1

if errorlevel 1 (
    echo ERROR: Failed to create/start wslg-pulse-bridge.service
    exit /b 1
)

if not exist ".env" (
    echo .env not found. Creating from .env.example...
    copy /Y ".env.example" ".env" >nul
)

echo [3/4] Updating .env pulse settings...
set "PULSE_SERVER_VALUE=tcp:%WSL_IP%:4713"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='.env'; $txt=Get-Content $p -Raw; $server='PULSE_SERVER=' + $env:PULSE_SERVER_VALUE; $source='PULSE_SOURCE=RDPSource'; if($txt -match '(?m)^PULSE_SERVER='){ $txt=[regex]::Replace($txt,'(?m)^PULSE_SERVER=.*$',$server) } else { $txt=$txt.TrimEnd() + [Environment]::NewLine + $server + [Environment]::NewLine }; if($txt -match '(?m)^PULSE_SOURCE='){ $txt=[regex]::Replace($txt,'(?m)^PULSE_SOURCE=.*$',$source) } else { $txt=$txt.TrimEnd() + [Environment]::NewLine + $source + [Environment]::NewLine }; Set-Content -Path $p -Value $txt -Encoding UTF8"

if errorlevel 1 (
    echo ERROR: Failed to update .env
    exit /b 1
)

echo [4/4] Recreating monitor-api container...
docker compose up -d --force-recreate monitor-api
if errorlevel 1 (
    echo ERROR: Failed to recreate monitor-api
    exit /b 1
)

echo Done. Pulse bridge + .env updated and monitor-api restarted.
echo You can now test Telegram command: /test
exit /b 0

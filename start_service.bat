@echo off
setlocal EnableDelayedExpansion

set "DISTRO=%~1"
set "WSL_TARGET="
set "DISTRO_LABEL=default"
set "BRIDGE_SERVICE=wslg-pulse-bridge.service"
set "BRIDGE_PORT="
set "BRIDGE_SOURCE="

if not "%DISTRO%"=="" (
    set "WSL_TARGET=-d %DISTRO%"
    set "DISTRO_LABEL=%DISTRO%"
)

echo [1/10] Ensuring Docker daemon is running...
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker daemon is not reachable. Attempting to start Docker Desktop...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$candidates=@(); if($env:ProgramFiles){$candidates += (Join-Path $env:ProgramFiles 'Docker\\Docker\\Docker Desktop.exe')}; if(${env:ProgramFiles(x86)}){$candidates += (Join-Path ${env:ProgramFiles(x86)} 'Docker\\Docker\\Docker Desktop.exe')}; $exe=$candidates ^| Where-Object { Test-Path $_ } ^| Select-Object -First 1; if(-not $exe){ exit 1 }; Start-Process -FilePath $exe ^| Out-Null"
    if errorlevel 1 goto :fail_docker_start
    echo Waiting for Docker daemon to become ready...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 60;$i++){ docker info >$null 2>&1; if($LASTEXITCODE -eq 0){$ok=$true; break}; Start-Sleep -Seconds 2 }; if(-not $ok){ exit 1 }"
    if errorlevel 1 goto :fail_docker_ready
)
echo Docker daemon is ready.

echo [2/10] Cleaning stale leftovers from previous runs...
docker compose down --remove-orphans >nul 2>&1
wsl %WSL_TARGET% -u root -- bash -lc "systemctl stop %BRIDGE_SERVICE% >/dev/null 2>&1 || true; systemctl kill %BRIDGE_SERVICE% >/dev/null 2>&1 || true; systemctl disable %BRIDGE_SERVICE% >/dev/null 2>&1 || true; systemctl reset-failed %BRIDGE_SERVICE% >/dev/null 2>&1 || true"

echo [3/10] Resolving WSL IP for distro "%DISTRO_LABEL%"...
set "WSL_IP="
for /f "usebackq delims=" %%i in (`wsl %WSL_TARGET% -- bash -lc "hostname -I | awk '{print $1}'"`) do (
    if not defined WSL_IP set "WSL_IP=%%i"
)
if not defined WSL_IP goto :fail_wsl
set "WSL_IP=%WSL_IP: =%"
echo WSL IP: %WSL_IP%

echo [4/10] Ensuring required WSL audio tooling...
wsl %WSL_TARGET% -u root -- bash -lc "command -v socat >/dev/null 2>&1 || (apt-get update && apt-get install -y socat pulseaudio-utils iproute2 procps)"
if errorlevel 1 goto :fail_packages

echo [5/10] Selecting a free TCP port for Pulse bridge...
set "BRIDGE_PORT_FILE=%TEMP%\wsl_pulse_bridge_port.txt"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$lines = wsl %WSL_TARGET% -- bash -lc 'ss -ltnH'; $used = New-Object 'System.Collections.Generic.HashSet[int]'; foreach($line in $lines){ $parts = ($line -split '\s+'); if($parts.Length -ge 4){ $local = $parts[3]; if($local -match ':(\d+)$'){ [void]$used.Add([int]$matches[1]) } } }; $p = 4713; while($used.Contains($p)){ $p++ }; Set-Content -Path $env:BRIDGE_PORT_FILE -Value $p -Encoding ASCII"
if errorlevel 1 goto :fail_bridge_port
set /p BRIDGE_PORT=<"%BRIDGE_PORT_FILE%"
del /q "%BRIDGE_PORT_FILE%" >nul 2>&1
if not defined BRIDGE_PORT goto :fail_bridge_port
echo Selected bridge port: %BRIDGE_PORT%

echo [6/10] Configuring and starting WSL pulse bridge service...
set "SERVICE_TMP=%TEMP%\wslg-pulse-bridge.service"
(
    echo [Unit]
    echo Description=Bridge WSLg Pulse socket to TCP %BRIDGE_PORT%
    echo After=network.target
    echo.
    echo [Service]
    echo Type=simple
    echo ExecStart=/usr/bin/socat TCP-LISTEN:%BRIDGE_PORT%,fork,reuseaddr UNIX-CONNECT:/mnt/wslg/PulseServer
    echo Restart=always
    echo RestartSec=2
    echo.
    echo [Install]
    echo WantedBy=multi-user.target
) > "%SERVICE_TMP%"
wsl %WSL_TARGET% -u root -- sh -c "cat > /etc/systemd/system/%BRIDGE_SERVICE%" < "%SERVICE_TMP%"
if errorlevel 1 goto :fail_service
wsl %WSL_TARGET% -u root -- bash -lc "systemctl daemon-reload && systemctl disable %BRIDGE_SERVICE% >/dev/null 2>&1 || true; systemctl reset-failed %BRIDGE_SERVICE% >/dev/null 2>&1 || true; systemctl start %BRIDGE_SERVICE% && systemctl is-active --quiet %BRIDGE_SERVICE%"
del /q "%SERVICE_TMP%" >nul 2>&1
if errorlevel 1 goto :fail_service

echo [7/10] Discovering usable Pulse source...
set "BRIDGE_SOURCE_FILE=%TEMP%\wsl_pulse_source.txt"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$source=''; $lines = wsl %WSL_TARGET% -- bash -lc 'pactl -s unix:/mnt/wslg/PulseServer list short sources 2>/dev/null'; foreach($line in $lines){ $parts = ($line -split '\s+'); if($parts.Length -ge 2 -and -not $parts[1].EndsWith('.monitor')){ $source = $parts[1]; break } }; if(-not $source){ $info = wsl %WSL_TARGET% -- bash -lc 'pactl -s unix:/mnt/wslg/PulseServer info 2>/dev/null'; foreach($line in $info){ if($line -match '^Default Source:\s*(.+)$'){ $source = $matches[1].Trim(); break } } }; if(-not $source){ $source='default' }; Set-Content -Path $env:BRIDGE_SOURCE_FILE -Value $source -Encoding ASCII"
if errorlevel 1 goto :fail_source
set /p BRIDGE_SOURCE=<"%BRIDGE_SOURCE_FILE%"
del /q "%BRIDGE_SOURCE_FILE%" >nul 2>&1
if not defined BRIDGE_SOURCE set "BRIDGE_SOURCE=default"
echo Selected pulse source: %BRIDGE_SOURCE%

if not exist ".env" (
    echo .env not found. Creating from .env.example...
    copy /Y ".env.example" ".env" >nul
    if errorlevel 1 goto :fail_env
)

echo [8/10] Updating .env runtime values...
set "PULSE_SERVER_VALUE=tcp:%WSL_IP%:%BRIDGE_PORT%"
set "PULSE_SOURCE_VALUE=%BRIDGE_SOURCE%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='.env'; $txt=Get-Content $p -Raw; $pairs=@{ 'PULSE_SERVER'=('PULSE_SERVER=' + $env:PULSE_SERVER_VALUE); 'PULSE_SOURCE'=('PULSE_SOURCE=' + $env:PULSE_SOURCE_VALUE); 'ENABLE_TELEGRAM_POLLER'='ENABLE_TELEGRAM_POLLER=true'; 'ENABLE_TELEGRAM_TEST_COMMAND'='ENABLE_TELEGRAM_TEST_COMMAND=true' }; foreach($k in $pairs.Keys){ $line=$pairs[$k]; if($txt -match ('(?m)^' + [regex]::Escape($k) + '=')){ $txt=[regex]::Replace($txt,'(?m)^' + [regex]::Escape($k) + '=.*$',$line) } else { $txt=$txt.TrimEnd() + [Environment]::NewLine + $line + [Environment]::NewLine } }; Set-Content -Path $p -Value $txt -Encoding UTF8"
if errorlevel 1 goto :fail_env

echo [9/10] Starting E2E compose stack (monitor + monitor-api)...
docker compose up -d --build monitor monitor-api
if errorlevel 1 goto :fail_compose

echo [10/10] Running readiness and audio operational checks...
docker compose ps
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 30;$i++){ try { $r=Invoke-WebRequest -UseBasicParsing http://localhost:8080/health -TimeoutSec 2; if($r.StatusCode -eq 200){$ok=$true; break} } catch {}; Start-Sleep -Seconds 1 }; if(-not $ok){ exit 1 }"
if errorlevel 1 goto :fail_health

docker compose exec -T monitor-api python -c "from pathlib import Path; import tempfile; from baby_cry_detection.monitor.audio import capture_audio_clip; output_dir = Path(tempfile.gettempdir()); clip_path, mode = capture_audio_clip(seconds=1.0, sample_rate=16000, output_dir=output_dir); print(f'Audio capture OK via {mode}: {clip_path}'); clip_path.unlink(missing_ok=True)"
if errorlevel 1 goto :fail_audio

echo.
echo E2E stack is ready.
echo - Pulse bridge: tcp:%WSL_IP%:%BRIDGE_PORT%
echo - Pulse source: %BRIDGE_SOURCE%
echo - Telegram commands: /status and /test
echo - Continuous cry monitoring: monitor service is running
echo - To stop all: stop_service.bat
exit /b 0

:fail_wsl
echo ERROR: Could not resolve WSL IP. Provide distro explicitly, e.g. start_service.bat Ubuntu
echo Available distros:
wsl -l -q
goto :pause_fail

:fail_packages
echo ERROR: Failed installing or checking WSL packages (socat/pulseaudio-utils/iproute2/procps).
goto :pause_fail

:fail_bridge_port
echo ERROR: Failed to pick a free TCP port for the Pulse bridge.
goto :pause_fail

:fail_service
echo ERROR: Failed configuring or starting WSL pulse bridge service.
echo Bridge service status:
wsl %WSL_TARGET% -u root -- bash -lc "systemctl status %BRIDGE_SERVICE% --no-pager -l"
goto :pause_fail

:fail_source
echo ERROR: Failed to detect a usable Pulse source from WSLg.
goto :pause_fail

:fail_env
echo ERROR: Failed updating .env for runtime values.
goto :pause_fail

:fail_compose
echo ERROR: Failed starting Docker compose stack.
goto :pause_fail

:fail_health
echo ERROR: monitor-api health check did not become ready.
goto :pause_fail

:fail_docker_start
echo ERROR: Docker daemon is unavailable and Docker Desktop could not be started automatically.
echo Start Docker Desktop manually, wait for it to finish starting, then rerun this script.
goto :pause_fail

:fail_docker_ready
echo ERROR: Docker Desktop was launched but the Docker daemon did not become ready in time.
echo Wait until Docker Desktop shows "Engine running" and rerun this script.
goto :pause_fail

:fail_audio
echo ERROR: Container audio capture check failed.
echo monitor-api pulse sources:
docker compose exec -T monitor-api pactl list short sources
echo.
echo Recent monitor logs:
docker compose logs --no-color --tail=120 monitor
goto :pause_fail

:pause_fail
echo.
echo Startup failed.
exit /b 1

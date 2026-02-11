@echo off
setlocal

set "DISTRO=%~1"
set "WSL_TARGET="
set "DISTRO_LABEL=default"
if not "%DISTRO%"=="" (
  set "WSL_TARGET=-d %DISTRO%"
  set "DISTRO_LABEL=%DISTRO%"
)

echo Current .env settings:
for %%K in (AUDIO_DEVICE PULSE_SERVER PULSE_SOURCE) do (
  for /f "tokens=1,* delims==" %%A in ('findstr /b /c:"%%K=" .env 2^>nul') do echo   %%A=%%B
)

echo.
echo WSL Pulse sources (%DISTRO_LABEL%):
wsl %WSL_TARGET% -- bash -lc "pactl list short sources"
if errorlevel 1 (
  echo.
  echo ERROR: Could not query WSL Pulse sources.
  echo Available distros:
  wsl -l -q
  exit /b 1
)

echo.
echo Container PortAudio devices (if service running):
docker compose exec monitor-api python -c "import sounddevice as sd; print(sd.query_devices())" 2>nul
if errorlevel 1 (
  echo   monitor-api not running or no PortAudio devices visible.
)

echo.
echo Hint:
echo - For Pulse bridge mode, set PULSE_SOURCE to one of WSL source names.
echo - For direct PortAudio mode, set AUDIO_DEVICE to numeric id/name visible in container.

exit /b 0

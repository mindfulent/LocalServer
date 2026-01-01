@echo off
setlocal enabledelayedexpansion

echo =============================================
echo    Sync Production World
echo =============================================
echo.
echo This script downloads the production world from Bloom.host
echo to your local test server.
echo.

set "LOCALSERVER_DIR=%~dp0.."
set "MCC_DIR=%~dp0..\..\MCC"

:: Check if local server is running (check for session.lock)
if exist "%LOCALSERVER_DIR%\world-production\session.lock" (
    echo WARNING: Local server may be running!
    echo Please stop the server before syncing world data.
    echo.
    set /p "CONTINUE=Continue anyway? (y/n): "
    if /i not "!CONTINUE!"=="y" (
        echo Cancelled.
        pause
        exit /b 1
    )
)

:: Check if MCC directory exists
if not exist "%MCC_DIR%\server-config.py" (
    echo ERROR: server-config.py not found at %MCC_DIR%
    echo Make sure the MCC directory is at the same level as LocalServer.
    pause
    exit /b 1
)

:: Run the download command
echo.
echo Starting world download...
echo.
cd /d "%MCC_DIR%"
python server-config.py download-world "%LOCALSERVER_DIR%"

if errorlevel 1 (
    echo.
    echo World sync failed!
    pause
    exit /b 1
)

echo.
echo =============================================
echo    World Sync Complete
echo =============================================
echo.
echo Production world data has been downloaded to:
echo   %LOCALSERVER_DIR%\world-production\
echo.
echo To use this world:
echo   1. Run scripts\production-mode.bat (or edit server.properties)
echo   2. Set level-name=world-production
echo   3. Run start.bat
echo.
pause

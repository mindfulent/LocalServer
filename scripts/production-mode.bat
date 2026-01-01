@echo off
setlocal enabledelayedexpansion
echo =============================================
echo    Production Mode Setup
echo =============================================
echo.
echo This mode replicates production settings:
echo   - Normal world generation (not superflat)
echo   - Mobs enabled
echo   - Configs synced from MCC
echo   - Production-like server.properties
echo.

set LOCALSERVER_DIR=%~dp0..
set MCC_DIR=%~dp0..\..\MCC

cd /d "%LOCALSERVER_DIR%"

:: Check if MCC exists
if not exist "%MCC_DIR%\config" (
    echo ERROR: MCC config folder not found at %MCC_DIR%\config
    pause
    exit /b 1
)

:: Swap server.properties to production mode
echo [1/3] Switching to production server.properties...
if exist "server.properties.test" (
    copy /y "server.properties" "server.properties.backup" >nul 2>&1
)
copy /y "server.properties.production" "server.properties" >nul
echo       Done.

:: Sync configs from MCC
echo.
echo [2/3] Syncing configs from MCC...
if not exist "config" mkdir config

:: Copy each config file/folder
for /d %%d in ("%MCC_DIR%\config\*") do (
    echo       Copying: %%~nxd
    xcopy /s /y /q "%%d" "config\%%~nxd\" >nul 2>&1
)
for %%f in ("%MCC_DIR%\config\*.*") do (
    echo       Copying: %%~nxf
    copy /y "%%f" "config\" >nul 2>&1
)
echo       Done.

:: Note about world
echo.
echo [3/3] World setup...
if exist "world-production" (
    echo       Using existing world-production folder.
    echo       To reset, delete world-production folder manually.
) else (
    echo       A new 'world-production' will be generated on first start.
)

echo.
echo =============================================
echo    Production Mode Ready
echo =============================================
echo.
echo Settings applied:
echo   - server.properties: production mode
echo   - Configs: synced from MCC
echo   - World: world-production (normal generation)
echo.
echo To start the server, run: start.bat
echo To return to test mode, run: scripts\test-mode.bat
echo.
pause

@echo off
echo =============================================
echo    Test Mode Setup
echo =============================================
echo.
echo Switching back to test settings:
echo   - Superflat world
echo   - Peaceful difficulty
echo   - No mobs
echo.

set LOCALSERVER_DIR=%~dp0..
cd /d "%LOCALSERVER_DIR%"

:: Swap server.properties to test mode
echo Switching to test server.properties...
copy /y "server.properties.test" "server.properties" >nul
echo Done.

echo.
echo =============================================
echo    Test Mode Ready
echo =============================================
echo.
echo Settings applied:
echo   - server.properties: test mode (superflat, peaceful)
echo   - World: world-test
echo.
echo To start the server, run: start.bat
echo.
pause

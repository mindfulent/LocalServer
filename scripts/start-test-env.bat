@echo off
title MCC Test Environment Launcher
color 0A

echo =============================================
echo    MCC Test Environment Launcher
echo =============================================
echo.

:: Check if packwiz serve is already running
netstat -ano | findstr ":8080" > nul
if %errorlevel% == 0 (
    echo [OK] Packwiz serve appears to be running
) else (
    echo [STARTING] Packwiz serve...
    start "Packwiz Serve" cmd /k "cd /d C:\Users\slash\Projects\MCC && packwiz.exe serve"
    timeout /t 3 /nobreak > nul
)

echo.
echo [STARTING] Test Server...
start "MCC Test Server" cmd /k "cd /d C:\Users\slash\Projects\LocalServer && start.bat"

echo.
echo =============================================
echo Test environment started!
echo.
echo - Packwiz:  http://localhost:8080/pack.toml
echo - Server:   localhost:25565
echo - RCON:     localhost:25575 (pw: testpassword)
echo =============================================
echo.
echo Press any key to launch Prism Launcher...
pause > nul

:: Launch Prism Launcher
start "" "C:\Users\slash\AppData\Local\Programs\PrismLauncher\prismlauncher.exe"

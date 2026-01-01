@echo off
setlocal enabledelayedexpansion
echo =============================================
echo    Test Specific Modpack Version
echo =============================================
echo.

set MCC_DIR=%~dp0..\..\MCC
set LOCALSERVER_DIR=%~dp0..

:: Check MCC directory exists
if not exist "%MCC_DIR%\pack.toml" (
    echo ERROR: MCC directory not found at %MCC_DIR%
    echo Expected pack.toml at that location.
    pause
    exit /b 1
)

:: Move to MCC directory
pushd "%MCC_DIR%"

:: Check for uncommitted changes
git diff --quiet 2>nul
if errorlevel 1 (
    echo WARNING: You have uncommitted changes in MCC.
    echo.
    git status --short
    echo.
    set /p STASH="Stash changes before continuing? (y/n): "
    if /i "!STASH!"=="y" (
        git stash push -m "Auto-stash before version testing"
        set DID_STASH=1
    ) else (
        echo Cancelled. Commit or stash your changes first.
        popd
        pause
        exit /b 1
    )
)

:: List available tags
echo.
echo Available version tags:
echo -----------------------
git tag --sort=-v:refname | head -15
echo.
echo (Showing latest 15 tags)
echo.

:: Prompt for version
set /p VERSION="Enter version tag to test (e.g., v0.9.52): "

if "%VERSION%"=="" (
    echo No version entered. Cancelled.
    if defined DID_STASH (
        git stash pop
    )
    popd
    pause
    exit /b 1
)

:: Check tag exists
git rev-parse "%VERSION%" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Tag '%VERSION%' does not exist.
    if defined DID_STASH (
        git stash pop
    )
    popd
    pause
    exit /b 1
)

:: Checkout the tag
echo.
echo Checking out %VERSION%...
git checkout "%VERSION%"

if errorlevel 1 (
    echo ERROR: Failed to checkout %VERSION%.
    if defined DID_STASH (
        git stash pop
    )
    popd
    pause
    exit /b 1
)

:: Start packwiz serve in background
echo.
echo Starting packwiz serve for %VERSION%...
start "Packwiz Serve (%VERSION%)" cmd /k "cd /d "%MCC_DIR%" && packwiz.exe serve"

:: Wait for packwiz to start
echo Waiting for packwiz serve to start...
timeout /t 3 /nobreak >nul

:: Check if packwiz is serving
curl -s http://localhost:8080/pack.toml >nul 2>&1
if errorlevel 1 (
    echo WARNING: packwiz serve may not have started. Check the other window.
)

:: Return to LocalServer and start
popd
echo.
echo =============================================
echo Starting LocalServer with %VERSION%...
echo =============================================
echo.
echo When done testing, remember to:
echo   1. Stop the server
echo   2. Close the packwiz serve window
echo   3. Run: cd ..\MCC ^&^& git checkout main
if defined DID_STASH (
    echo   4. Run: git stash pop
)
echo.
pause

:: Start the server
cd /d "%LOCALSERVER_DIR%"
call start.bat

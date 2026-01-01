@echo off
setlocal enabledelayedexpansion
echo =============================================
echo    Clear Mods (Keep Fabric API Only)
echo =============================================
echo.

cd /d "%~dp0.."

if not exist "mods" (
    echo No mods folder found.
    pause
    exit /b
)

:: Count mods before
set BEFORE=0
for %%f in (mods\*.jar) do set /a BEFORE+=1

echo Found %BEFORE% mod(s) in mods folder.
echo.
echo This will remove all mods EXCEPT Fabric API.
echo Fabric API will be preserved for vanilla+ testing.
echo.
set /p CONFIRM="Proceed? (y/n): "
if /i not "%CONFIRM%"=="y" (
    echo Cancelled.
    pause
    exit /b
)

echo.
echo Removing mods...

:: Remove all jars except fabric-api
for %%f in (mods\*.jar) do (
    echo %%~nf | findstr /i "fabric-api" >nul
    if errorlevel 1 (
        echo   Removing: %%~nxf
        del "%%f"
    ) else (
        echo   Keeping:  %%~nxf
    )
)

:: Also remove .pw.toml files (packwiz metadata)
if exist "mods\*.pw.toml" (
    echo.
    echo Removing packwiz metadata files...
    del /q "mods\*.pw.toml" 2>nul
)

:: Count mods after
set AFTER=0
for %%f in (mods\*.jar) do set /a AFTER+=1

echo.
echo =============================================
echo Done! %BEFORE% mods reduced to %AFTER%.
echo =============================================
pause

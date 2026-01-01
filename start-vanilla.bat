@echo off
setlocal enabledelayedexpansion
title Vanilla Test Server - 1.21.1 Fabric
echo =============================================
echo    Vanilla Test Server (No Modpack Mods)
echo =============================================
echo.

:: Java 21 path (bundled with Prism Launcher)
set JAVA_PATH=C:\Users\slash\AppData\Roaming\PrismLauncher\java\java-runtime-delta\bin\java.exe

:: Check if mods folder has content beyond Fabric API
set MOD_COUNT=0
for %%f in (mods\*.jar) do set /a MOD_COUNT+=1

if %MOD_COUNT% GTR 1 (
    echo WARNING: Found %MOD_COUNT% mods in mods folder.
    echo For true vanilla testing, run scripts\clear-mods.bat first.
    echo.
    set /p CONTINUE="Continue anyway? (y/n): "
    if /i not "!CONTINUE!"=="y" (
        echo Cancelled.
        pause
        exit /b
    )
)

echo Starting vanilla server (no packwiz sync)...
echo.

:: Optimized JVM flags for local testing (4GB allocation)
"%JAVA_PATH%" -Xms4G -Xmx4G ^
  -XX:+UseG1GC ^
  -XX:+ParallelRefProcEnabled ^
  -XX:MaxGCPauseMillis=200 ^
  -XX:+UnlockExperimentalVMOptions ^
  -XX:+DisableExplicitGC ^
  -XX:+AlwaysPreTouch ^
  -XX:G1NewSizePercent=30 ^
  -XX:G1MaxNewSizePercent=40 ^
  -XX:G1HeapRegionSize=8M ^
  -XX:G1ReservePercent=20 ^
  -XX:G1HeapWastePercent=5 ^
  -XX:G1MixedGCCountTarget=4 ^
  -XX:InitiatingHeapOccupancyPercent=15 ^
  -XX:G1MixedGCLiveThresholdPercent=90 ^
  -XX:G1RSetUpdatingPauseTimePercent=5 ^
  -XX:SurvivorRatio=32 ^
  -XX:+PerfDisableSharedMem ^
  -XX:MaxTenuringThreshold=1 ^
  -jar fabric-server-launch.jar nogui

pause

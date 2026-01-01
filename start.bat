@echo off
title MCC Test Server - 1.21.1 Fabric
echo Starting MCC Test Server...
echo.

:: Java 21 path (bundled with Prism Launcher)
set JAVA_PATH=C:\Users\slash\AppData\Roaming\PrismLauncher\java\java-runtime-delta\bin\java.exe

:: Update mods from local packwiz serve (if running)
echo Checking for packwiz updates...
if exist packwiz-installer-bootstrap.jar (
    "%JAVA_PATH%" -jar packwiz-installer-bootstrap.jar -g -s server http://localhost:8080/pack.toml
    if errorlevel 1 (
        echo Warning: Could not update from packwiz. Continuing with existing mods...
    )
) else (
    echo Note: packwiz-installer-bootstrap.jar not found. Skipping mod sync.
)

echo.
echo Starting server...

:: Optimized JVM flags for local testing (4GB allocation)
:: Reduced from production 12GB since client also needs RAM
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

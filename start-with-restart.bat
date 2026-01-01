@echo off
title MCC Test Server (Auto-Restart)

:: Java 21 path (bundled with Prism Launcher)
set JAVA_PATH=C:\Users\slash\AppData\Roaming\PrismLauncher\java\java-runtime-delta\bin\java.exe

:loop
echo Starting server...
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

echo.
echo Server stopped. Restarting in 5 seconds...
echo Press Ctrl+C to exit.
timeout /t 5
goto loop

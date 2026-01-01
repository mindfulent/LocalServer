@echo off
echo =============================================
echo    Reset Test World
echo =============================================
echo.
echo This will DELETE the test world and generate a new one.
echo.
set /p confirm="Are you sure? (y/n): "
if /i "%confirm%" neq "y" goto :end

cd /d C:\Users\slash\Projects\LocalServer

:: Remove world directories
if exist "world-test" rmdir /s /q "world-test"
if exist "world-test_nether" rmdir /s /q "world-test_nether"
if exist "world-test_the_end" rmdir /s /q "world-test_the_end"

echo.
echo [OK] Test world deleted. A new world will be generated on next server start.
echo.

:end
pause

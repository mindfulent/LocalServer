# sync-to-test-server.ps1
# Syncs server-side mods from packwiz to local test server

$PackwizDir = "C:\Users\slash\Projects\MCC"
$TestServerDir = "C:\Users\slash\Projects\LocalServer"
$PackwizExe = "$PackwizDir\packwiz.exe"

Write-Host "Refreshing packwiz index..." -ForegroundColor Cyan
Set-Location $PackwizDir
& $PackwizExe refresh

Write-Host "Exporting mrpack..." -ForegroundColor Cyan
& $PackwizExe modrinth export

# Find the exported mrpack file
$MrpackFile = Get-ChildItem -Path $PackwizDir -Filter "*.mrpack" | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if ($MrpackFile) {
    Write-Host "Found mrpack: $($MrpackFile.Name)" -ForegroundColor Green
    Write-Host ""
    Write-Host "Note: To install mods to the test server, use mrpack-install or" -ForegroundColor Yellow
    Write-Host "start the test server with packwiz serve running." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Alternatively, run the test server - it will auto-update from packwiz serve." -ForegroundColor Yellow
} else {
    Write-Host "ERROR: No mrpack file found" -ForegroundColor Red
}

Write-Host ""
Write-Host "Sync preparation complete!" -ForegroundColor Green

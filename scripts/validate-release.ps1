# validate-release.ps1
# Downloads an MCC release mrpack from GitHub and extracts it for testing
# This validates the exact artifact that players download

param(
    [Parameter(Mandatory=$false)]
    [string]$Version
)

$ErrorActionPreference = "Stop"
$LocalServerDir = Split-Path -Parent $PSScriptRoot
$TempDir = Join-Path $LocalServerDir "temp-mrpack"
$ModsDir = Join-Path $LocalServerDir "mods"
$OverridesDir = Join-Path $LocalServerDir "overrides-temp"

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "   Validate MCC Release" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# If no version provided, fetch latest releases and prompt
if (-not $Version) {
    Write-Host "Fetching available releases from GitHub..." -ForegroundColor Yellow

    try {
        $releases = Invoke-RestMethod -Uri "https://api.github.com/repos/mindfulent/MCC/releases" -Headers @{Accept="application/vnd.github.v3+json"}
        $latestReleases = $releases | Select-Object -First 10

        Write-Host ""
        Write-Host "Recent releases:" -ForegroundColor Green
        Write-Host "-----------------------"
        $i = 1
        foreach ($release in $latestReleases) {
            Write-Host "  $i. $($release.tag_name) - $($release.name)"
            $i++
        }
        Write-Host ""

        $Version = Read-Host "Enter version tag (e.g., v0.9.52)"

        if (-not $Version) {
            Write-Host "No version entered. Cancelled." -ForegroundColor Red
            exit 1
        }
    }
    catch {
        Write-Host "Failed to fetch releases: $_" -ForegroundColor Red
        Write-Host ""
        $Version = Read-Host "Enter version tag manually (e.g., v0.9.52)"
    }
}

# Normalize version (ensure 'v' prefix for tag, remove for filename)
$TagVersion = if ($Version.StartsWith("v")) { $Version } else { "v$Version" }
$FileVersion = $TagVersion.TrimStart("v")

# Construct download URL
$MrpackUrl = "https://github.com/mindfulent/MCC/releases/download/$TagVersion/MCC-$FileVersion.mrpack"
$MrpackFile = Join-Path $TempDir "MCC-$FileVersion.mrpack"

Write-Host ""
Write-Host "Downloading: $MrpackUrl" -ForegroundColor Yellow

# Create temp directory
if (Test-Path $TempDir) {
    Remove-Item -Recurse -Force $TempDir
}
New-Item -ItemType Directory -Path $TempDir | Out-Null

# Download mrpack
try {
    Invoke-WebRequest -Uri $MrpackUrl -OutFile $MrpackFile
    Write-Host "Downloaded: $MrpackFile" -ForegroundColor Green
}
catch {
    Write-Host "ERROR: Failed to download mrpack" -ForegroundColor Red
    Write-Host "URL: $MrpackUrl" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    Remove-Item -Recurse -Force $TempDir -ErrorAction SilentlyContinue
    exit 1
}

# Extract mrpack (it's a zip file)
Write-Host ""
Write-Host "Extracting mrpack..." -ForegroundColor Yellow
$ExtractDir = Join-Path $TempDir "extracted"
Expand-Archive -Path $MrpackFile -DestinationPath $ExtractDir

# Read modrinth.index.json to get mod list
$IndexFile = Join-Path $ExtractDir "modrinth.index.json"
if (-not (Test-Path $IndexFile)) {
    Write-Host "ERROR: modrinth.index.json not found in mrpack" -ForegroundColor Red
    exit 1
}

$Index = Get-Content $IndexFile | ConvertFrom-Json
Write-Host "Modpack: $($Index.name) v$($Index.versionId)" -ForegroundColor Cyan
Write-Host "Minecraft: $($Index.dependencies.'minecraft')" -ForegroundColor Cyan
Write-Host "Mods to download: $($Index.files.Count)" -ForegroundColor Cyan

# Clear existing mods (except Fabric API if user wants to keep it)
Write-Host ""
$ClearMods = Read-Host "Clear existing mods folder? (y/n)"
if ($ClearMods -eq "y") {
    Write-Host "Clearing mods folder..." -ForegroundColor Yellow
    Get-ChildItem -Path $ModsDir -Filter "*.jar" | ForEach-Object {
        # Keep fabric-api
        if ($_.Name -notmatch "fabric-api") {
            Remove-Item $_.FullName -Force
            Write-Host "  Removed: $($_.Name)" -ForegroundColor DarkGray
        } else {
            Write-Host "  Kept: $($_.Name)" -ForegroundColor Green
        }
    }
    # Remove pw.toml files
    Get-ChildItem -Path $ModsDir -Filter "*.pw.toml" -ErrorAction SilentlyContinue | Remove-Item -Force
}

# Download mods from mrpack manifest
Write-Host ""
Write-Host "Downloading mods..." -ForegroundColor Yellow
$downloaded = 0
$failed = 0

foreach ($file in $Index.files) {
    # Only download server-side or both-side mods
    $env = $file.env
    if ($env -and $env.server -eq "unsupported") {
        Write-Host "  Skipping (client-only): $($file.path)" -ForegroundColor DarkGray
        continue
    }

    $destPath = Join-Path $LocalServerDir $file.path
    $destDir = Split-Path -Parent $destPath

    if (-not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }

    # Use first download URL
    $downloadUrl = $file.downloads[0]

    try {
        Invoke-WebRequest -Uri $downloadUrl -OutFile $destPath
        Write-Host "  Downloaded: $(Split-Path -Leaf $file.path)" -ForegroundColor Green
        $downloaded++
    }
    catch {
        Write-Host "  FAILED: $(Split-Path -Leaf $file.path) - $_" -ForegroundColor Red
        $failed++
    }
}

# Copy overrides
$OverridesSource = Join-Path $ExtractDir "overrides"
if (Test-Path $OverridesSource) {
    Write-Host ""
    Write-Host "Copying overrides (configs, etc.)..." -ForegroundColor Yellow
    Copy-Item -Path "$OverridesSource\*" -Destination $LocalServerDir -Recurse -Force
    Write-Host "  Overrides applied" -ForegroundColor Green
}

# Cleanup
Write-Host ""
Write-Host "Cleaning up temp files..." -ForegroundColor Yellow
Remove-Item -Recurse -Force $TempDir

# Summary
Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "   Validation Setup Complete" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Version:    $TagVersion" -ForegroundColor White
Write-Host "  Downloaded: $downloaded mods" -ForegroundColor Green
if ($failed -gt 0) {
    Write-Host "  Failed:     $failed mods" -ForegroundColor Red
}
Write-Host ""
Write-Host "To test, run: .\start-vanilla.bat" -ForegroundColor Yellow
Write-Host "(Uses start-vanilla to avoid packwiz overwriting the extracted mods)" -ForegroundColor DarkGray
Write-Host ""

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Local Minecraft 1.21.1 Fabric test server for Windows. Used to validate MCC modpack changes before deploying to production (Bloom.host).

## Testing Modes

| Mode | Script | Use Case |
|------|--------|----------|
| Development | `start.bat` | Test latest MCC with packwiz sync |
| Production | `scripts/production-mode.bat` | Replicate production experience |
| Vanilla | `start-vanilla.bat` | Test without mods |
| Version Testing | `scripts/test-version.bat` | Test specific MCC version tags |
| Release Validation | `scripts/validate-release.ps1` | Test exact mrpack artifact |

See `docs/TESTING-WORKFLOW.md` for detailed usage.

## Quick Start

```bash
# Development mode (most common)
cd ../MCC && ./packwiz.exe serve   # Terminal 1
./start.bat                         # Terminal 2

# Production mode (realistic testing)
scripts/production-mode.bat         # Switch settings + sync configs
start.bat                           # Start server

# Test specific version
scripts/test-version.bat            # Interactive: select version tag
```

Connect: `localhost:25565`

## Key Configuration

- **Java 21**: Prism Launcher's bundled JDK (`%APPDATA%\PrismLauncher\java\java-runtime-delta\`)
- **Fabric Loader**: 0.18.4+ required (download fresh `fabric-server-launch.jar` if needed)
- **RAM**: 4GB allocated (adjustable in start scripts)
- **Offline Mode**: `online-mode=false` for faster testing

## Ports

| Service | Port |
|---------|------|
| Minecraft Server | 25565 |
| RCON | 25575 (pw: `testpassword`) |
| Packwiz Serve | 8080 |
| BlueMap | 8100 |
| Voice Chat | 24454 |

## Directory Structure

```
LocalServer/
├── start.bat                    # Dev mode with packwiz sync
├── start-vanilla.bat            # No mods, no packwiz
├── server.properties.test       # Test settings (superflat, peaceful)
├── server.properties.production # Production settings (normal world)
├── scripts/
│   ├── production-mode.bat      # Switch to production + sync configs
│   ├── test-mode.bat            # Switch back to test mode
│   ├── test-version.bat         # Test specific MCC version
│   ├── validate-release.ps1     # Download + test mrpack
│   ├── clear-mods.bat           # Remove mods (keep Fabric API)
│   ├── start-test-env.bat       # All-in-one launcher
│   └── sync-world.bat           # Download production world data
└── docs/
    ├── TESTING-WORKFLOW.md      # Testing mode documentation
    └── LOCAL-GUIDE.md.txt       # Comprehensive setup guide
```

## Known Issues

- **CurseForge API exclusions**: Some mods (Axiom, First Person Model) can't be auto-downloaded via packwiz. Use `validate-release.ps1` to extract from mrpack instead.
- **AutoWhitelist warnings**: Expected in offline mode - safe to ignore for local testing.

## World Data Sync

Download production world data from Bloom.host for realistic local testing:

```bash
# Quick method (from LocalServer)
scripts\sync-world.bat

# Or via MCC server-config.py
cd ../MCC
python server-config.py download-world             # Interactive
python server-config.py download-world -y          # Non-interactive
python server-config.py download-world --no-backup # Skip local backup
```

**What it does:**
- Downloads `/world/`, `/world_nether/`, `/world_the_end/` from production
- Saves to `world-production/`, `world-production_nether/`, `world-production_the_end/`
- Backs up existing local world to `world-backup-YYYYMMDD_HHMMSS/`
- Warns if local server is running (session.lock check)

**Use cases:**
- Realistic testing with actual world state
- Bug reproduction in production environment
- Offline backup of server world

## Related Projects

| Directory | Purpose |
|-----------|---------|
| `../MCC/` | Packwiz modpack source |

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Local Minecraft 1.21.1 Fabric test server for Windows. Used to validate MCC modpack changes before deploying to production (Bloom.host).

## Server Manager (server-config.py)

Standalone Python script for managing the local test server. Provides an interactive menu and CLI commands.

```bash
# Interactive menu (recommended)
python server-config.py

# CLI commands
python server-config.py start              # Start server with packwiz sync
python server-config.py start --vanilla    # Start without mods
python server-config.py stop               # Stop via RCON
python server-config.py mode production    # Switch to production mode
python server-config.py mode test          # Switch to test mode
python server-config.py download-world     # Sync world from Bloom.host
python server-config.py reset-world test   # Delete test world
python server-config.py clear-mods         # Remove mods (keep Fabric API)
python server-config.py rcon "say hello"   # Send RCON command
python server-config.py status             # Show current state
python server-config.py version            # Show current MCC version
python server-config.py version list       # List all available versions
python server-config.py version v0.9.50    # Switch to specific version
python server-config.py version main       # Return to main branch
```

**Setup:** Copy `.env.example` to `.env` and fill in SFTP credentials for world sync.

## Testing Modes

| Mode | Script/Command | Use Case |
|------|----------------|----------|
| Development | `python server-config.py start` | Test latest MCC with packwiz sync |
| Production | `python server-config.py mode production` | Replicate production experience |
| Vanilla | `python server-config.py start --vanilla` | Test without mods |
| Version Testing | `scripts/test-version.bat` | Test specific MCC version tags |
| Release Validation | `scripts/validate-release.ps1` | Test exact mrpack artifact |

See `docs/TESTING-WORKFLOW.md` for detailed usage.

## Quick Start

```bash
# Interactive menu (easiest)
python server-config.py

# Development mode (most common)
cd ../MCC && ./packwiz.exe serve       # Terminal 1
python server-config.py start           # Terminal 2

# Production mode (realistic testing)
python server-config.py mode production  # Switch settings + sync configs
python server-config.py start            # Start server

# Test specific version
scripts/test-version.bat                 # Interactive: select version tag
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
├── server-config.py             # Server manager (interactive menu + CLI)
├── .env.example                 # SFTP credentials template
├── start.bat                    # Dev mode with packwiz sync
├── start-vanilla.bat            # No mods, no packwiz
├── server.properties.test       # Test settings (superflat, peaceful)
├── server.properties.production # Production settings (normal world)
├── world-production/            # Downloaded production world (backup)
├── world-local/                 # Working copy for production mode
├── distant-horizons-cold/       # Cold storage for DH SQLite files
│   ├── overworld/
│   ├── nether/
│   └── end/
├── scripts/
│   ├── test-version.bat         # Test specific MCC version
│   ├── validate-release.ps1     # Download + test mrpack
│   └── start-test-env.bat       # All-in-one launcher
└── docs/
    ├── TESTING-WORKFLOW.md      # Testing mode documentation
    └── LOCAL-GUIDE.md.txt       # Comprehensive setup guide
```

## Known Issues

- **CurseForge API exclusions**: Some mods (Axiom, First Person Model) can't be auto-downloaded via packwiz. Use `validate-release.ps1` to extract from mrpack instead.
- **AutoWhitelist warnings**: Expected in offline mode - safe to ignore for local testing.

## World Data Sync

Download/upload production world data from/to Bloom.host:

```bash
# Via interactive menu
python server-config.py
# d = Download world (excludes DH)
# D = Download world + DistantHorizons (full, rare)
# h = Download DistantHorizons (to cold storage)
# u = Upload world (server must be offline)
# H = Upload DistantHorizons (server can be online)

# Via CLI
python server-config.py download-world             # Download world (excludes DH)
python server-config.py download-world --full      # Include DistantHorizons
python server-config.py download-world -y          # Non-interactive
python server-config.py download-world --no-backup # Skip local backup
python server-config.py download-dh                # Download DH to cold storage
python server-config.py upload-world               # Upload world (server offline)
python server-config.py upload-dh                  # Upload DH from cold storage
```

**Requirements:** Configure `.env` with SFTP credentials (see `.env.example`).

**DistantHorizons files** are handled separately:
- Large LOD database files (~1-2GB total across dimensions)
- Excluded from normal world downloads by default
- Stored in `distant-horizons-cold/` for cold storage backup
- Can be uploaded while server is running (not a hard dependency)

**What download-world does:**
- Downloads `/world/`, `/world_nether/`, `/world_the_end/` from production
- Excludes DistantHorizons.sqlite files (use `--full` to include)
- Saves to `world-production/`, `world-production_nether/`, `world-production_the_end/`
- Backs up existing local world to `world-backup-YYYYMMDD_HHMMSS/`
- Shows elapsed time on completion

**Standard restore workflow:**
1. Server offline
2. `upload-world` - Upload world data
3. Server back online
4. `upload-dh` - (Optional) Upload DistantHorizons

**Use cases:**
- Realistic testing with actual world state
- Bug reproduction in production environment
- Offline backup of server world

## Modpack Version Management

Switch between MCC versions to test older releases or validate specific tags:

```bash
# Via interactive menu
python server-config.py
# Select 'l' to list versions, 'c' to change version, 'b' to return to main

# Via CLI
python server-config.py version              # Show current version
python server-config.py version list         # List all available versions
python server-config.py version v0.9.50      # Switch to specific version
python server-config.py version 0.9.50       # Also works without 'v' prefix
python server-config.py version main         # Return to main branch
```

**What it does:**
- Lists all git tags from MCC repository
- Checks out the specified tag in MCC
- Stashes uncommitted changes if present (auto-restores when returning to main)
- Auto-syncs mods from the selected version
- Cleans old mrpack files to ensure fresh export

**Workflow to test an older version:**
1. `python server-config.py version v0.9.45` - Switch MCC to that version
2. `python server-config.py reset-local` - (Optional) Reset world from backup
3. `python server-config.py start` - Start server with that version's mods

**Return to latest:**
```bash
python server-config.py version main  # Returns to main, offers to restore stashed changes
```

## Related Projects

| Directory | Purpose |
|-----------|---------|
| `../MCC/` | Packwiz modpack source |

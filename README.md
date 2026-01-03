# LocalServer

Local Minecraft 1.21.1 Fabric test server for validating [MCC modpack](https://github.com/mindfulent/MCC) changes before deploying to production (Bloom.host).

## Features

- **Fabric 1.21.1** with optimized JVM flags (Aikar's G1GC tuning)
- **Auto-sync from mrpack** - Extracts mods directly from `.mrpack` file (no API restrictions)
- **Offline mode** - No authentication for faster testing
- **Three server modes**: Production, Fresh World, and Vanilla Debug
- **Backup preservation** - Production mode uses a working copy, leaving backup untouched
- **RCON enabled** - Remote console for scripted commands
- **Automation scripts** - One-click environment launch

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| **Java 21** | Uses Prism Launcher's bundled JDK by default |
| **Packwiz** | Located at `../MCC/packwiz.exe` |
| **Prism Launcher** | For running the client |

## Quick Start

### Option 1: Interactive Menu (Recommended)

```bash
python server-config.py
```

Press **1** to start the server. Mods will auto-sync from the mrpack if needed.

### Option 2: Direct Start

```batch
python server-config.py start
```

Or use the batch file:
```batch
start.bat
```

### Connect

1. Launch your MCC instance in Prism Launcher
2. Go to **Multiplayer** → **Direct Connect**
3. Enter: `localhost`

## Server Modes

LocalServer supports three modes, managed via `python server-config.py`:

### Production Mode
- Uses `world-local/` - a **copy** of the production backup
- All modpack mods installed
- Normal world generation, mobs enabled
- Syncs configs from MCC
- **Primary use case**: Testing mods with real production world

### Fresh World Mode
- Uses `world-fresh/` - newly generated world
- All modpack mods installed
- Normal world generation, mobs enabled
- **Use case**: Testing mod initialization, clean slate scenarios

### Vanilla Debug Mode
- Uses `world-vanilla/` - newly generated world
- Only Fabric API installed (all other mods removed)
- **Use case**: Isolating mod issues, "does this crash without mods?"

**Backup preservation:** When switching to production mode, the server automatically copies `world-production/` (the backup from `world-download`) to `world-local/` (the working copy). This means:
- Your backup is never modified by LocalServer
- You can break things locally and reset anytime
- `world-upload` pushes the pristine backup, not local changes

### World Folders

| Folder | Purpose | Modified by LocalServer? |
|--------|---------|--------------------------|
| `world-production/` | Backup from production | **No** (pristine) |
| `world-local/` | Working copy for Production mode | Yes |
| `world-fresh/` | Fresh World mode | Yes |
| `world-vanilla/` | Vanilla Debug mode | Yes |

### Key Commands

```bash
python server-config.py                    # Interactive menu
python server-config.py start              # Start server (auto-syncs mods)
python server-config.py mode production    # Switch to production mode
python server-config.py mode fresh         # Switch to fresh world mode
python server-config.py mode vanilla       # Switch to vanilla debug mode
python server-config.py sync-mods          # Manually sync mods from mrpack
python server-config.py reset-local        # Reset world-local from backup
```

## Directory Structure

```
LocalServer/
├── docs/
│   └── LOCAL-GUIDE.md.txt       # Comprehensive setup guide
├── scripts/
│   ├── start-test-env.bat       # All-in-one environment launcher
│   └── sync-to-test-server.ps1  # Export mrpack from MCC
├── server.properties            # Active server configuration
├── server.properties.production # Production mode template
├── server.properties.fresh      # Fresh World mode template
├── server.properties.vanilla    # Vanilla Debug mode template
├── start.bat                    # Main server launcher
├── start-with-restart.bat       # Auto-restart on crash
├── eula.txt                     # Minecraft EULA acceptance
└── CLAUDE.md                    # Claude Code instructions
```

## Configuration

### Server Properties

| Setting | Value | Purpose |
|---------|-------|---------|
| `server-ip` | `127.0.0.1` | Localhost only |
| `online-mode` | `false` | Skip authentication |
| `level-type` | `minecraft:normal` | Standard world generation |
| `view-distance` | `12` | Balanced for local testing |
| `gamemode` | `creative` | Testing convenience |
| `difficulty` | `normal` | Mobs enabled for realistic testing |

### JVM Flags

The server uses 4GB RAM with Aikar's optimized G1GC flags. Edit `start.bat` to adjust:

```batch
-Xms4G -Xmx4G
```

**RAM Guidelines** (client + server on same machine):

| System RAM | Server | Client | OS/Other |
|------------|--------|--------|----------|
| 16 GB | 4 GB | 4 GB | 8 GB |
| 32 GB | 6 GB | 6 GB | 20 GB |

### Java Path

By default, uses Prism Launcher's bundled Java 21:

```
C:\Users\slash\AppData\Roaming\PrismLauncher\java\java-runtime-delta\bin\java.exe
```

To use a different Java installation, edit the `JAVA_PATH` variable in `start.bat`.

## Ports

| Service | Port | Protocol |
|---------|------|----------|
| Minecraft Server | 25565 | TCP |
| RCON | 25575 | TCP |

### RCON Access

```powershell
# Using mcrcon or similar tool
mcrcon -H localhost -P 25575 -p testpassword "say Hello"
```

## Mod Sync

LocalServer syncs mods by extracting them directly from the `.mrpack` file in MCC directory. This avoids CurseForge API restrictions that affect some mods (Axiom, First Person Model, etc.).

**How it works:**
1. On server start, checks if mods folder has <10 JARs
2. If mods missing, finds latest `MCC-*.mrpack` in `../MCC/`
3. If no mrpack exists, automatically runs `packwiz modrinth export`
4. Extracts bundled mods from the mrpack
5. Downloads any manifest-referenced mods from URLs

**Manual sync:** Press **'m'** in the menu or run `python server-config.py sync-mods`

## Development Workflow

```
┌─────────────────────────────────────────────────────────────┐
│  1. Edit modpack in ../MCC/                                 │
│     - Add/remove mods: packwiz cf install <mod>             │
│     - Edit configs in config/                               │
├─────────────────────────────────────────────────────────────┤
│  2. Export mrpack (or let server do it automatically)       │
│     cd ../MCC && packwiz modrinth export                    │
├─────────────────────────────────────────────────────────────┤
│  3. Start test server (auto-syncs mods from mrpack)         │
│     python server-config.py start                           │
├─────────────────────────────────────────────────────────────┤
│  4. Launch client & connect to localhost                    │
│     - Test the changes                                      │
│     - Check /spark tps, look for errors                     │
├─────────────────────────────────────────────────────────────┤
│  5. If tests pass → deploy to production                    │
│     python ../MCC/server-config.py update-pack X.Y.Z        │
│     python ../MCC/server-config.py restart                  │
└─────────────────────────────────────────────────────────────┘
```

## Troubleshooting

### Server Won't Start

| Error | Solution |
|-------|----------|
| "Unable to access jarfile" | Download `fabric-server-launch.jar` from [fabricmc.net](https://fabricmc.net/use/server/) |
| "Java version" error | Ensure Java 21 is installed; check `JAVA_PATH` in start.bat |
| "Port already in use" | Check `netstat -ano \| findstr :25565` and kill the process |

### Client Can't Connect

| Error | Solution |
|-------|----------|
| "Connection refused" | Server crashed or not running - check console |
| "Outdated server/client" | Version mismatch - both must be 1.21.1 |
| "Mod mismatch" | Re-sync using packwiz workflow |

### Mod Sync Issues

| Error | Solution |
|-------|----------|
| "No mrpack found" | Run `packwiz modrinth export` in MCC directory |
| "Failed to find or create mrpack" | Check that `../MCC/packwiz.exe` exists |
| Mods not updating | Delete mods folder and run `sync-mods` |

## First-Time Setup

If setting up from scratch (JARs not present):

```powershell
# Download Fabric server launcher
Invoke-WebRequest -Uri "https://meta.fabricmc.net/v2/versions/loader/1.21.1/0.16.9/1.0.1/server/jar" -OutFile "fabric-server-launch.jar"
```

## Related Projects

| Repository | Purpose |
|------------|---------|
| [MCC](https://github.com/mindfulent/MCC) | Packwiz modpack source |
| [minecraftcollege](https://github.com/mindfulent/minecraftcollege) | Community website |

## License

MIT

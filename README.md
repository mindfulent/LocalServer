# LocalServer

Local Minecraft 1.21.1 Fabric test server for validating [MCC modpack](https://github.com/mindfulent/MCC) changes before deploying to production (Bloom.host).

## Features

- **Fabric 1.21.1** with optimized JVM flags (Aikar's G1GC tuning)
- **Packwiz integration** - Auto-syncs mods from `packwiz serve`
- **Offline mode** - No authentication for faster testing
- **Flat world** - Clean testing surface with fast world generation
- **RCON enabled** - Remote console for scripted commands
- **Automation scripts** - One-click environment launch

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| **Java 21** | Uses Prism Launcher's bundled JDK by default |
| **Packwiz** | Located at `../MCC/packwiz.exe` |
| **Prism Launcher** | For running the client |

## Quick Start

### Option 1: All-in-One Launcher

```batch
scripts\start-test-env.bat
```

This will:
1. Start `packwiz serve` (if not running)
2. Launch the test server
3. Open Prism Launcher

### Option 2: Manual Start

```powershell
# Terminal 1: Start packwiz serve
cd ..\MCC
.\packwiz.exe serve

# Terminal 2: Start server
cd ..\LocalServer
.\start.bat
```

### Connect

1. Launch your MCC instance in Prism Launcher
2. Go to **Multiplayer** → **Direct Connect**
3. Enter: `localhost`

## Directory Structure

```
LocalServer/
├── docs/
│   └── LOCAL-GUIDE.md.txt     # Comprehensive setup guide
├── scripts/
│   ├── start-test-env.bat     # All-in-one environment launcher
│   ├── reset-test-world.bat   # Delete test world for fresh start
│   └── sync-to-test-server.ps1 # Export mrpack from MCC
├── start.bat                   # Main server launcher
├── start-with-restart.bat      # Auto-restart on crash
├── server.properties           # Server configuration
├── eula.txt                    # Minecraft EULA acceptance
└── CLAUDE.md                   # Claude Code instructions
```

## Configuration

### Server Properties

| Setting | Value | Purpose |
|---------|-------|---------|
| `server-ip` | `127.0.0.1` | Localhost only |
| `online-mode` | `false` | Skip authentication |
| `level-type` | `minecraft:flat` | Fast world gen |
| `view-distance` | `8` | Reduced for shared RAM |
| `gamemode` | `creative` | Testing convenience |
| `difficulty` | `peaceful` | No mob distractions |

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
| Packwiz Serve | 8080 | HTTP |

### RCON Access

```powershell
# Using mcrcon or similar tool
mcrcon -H localhost -P 25575 -p testpassword "say Hello"
```

## Scripts

### start-test-env.bat

Launches the complete test environment:
- Checks if packwiz serve is running, starts it if not
- Starts the Minecraft server
- Optionally launches Prism Launcher

### reset-test-world.bat

Deletes the test world directories (`world-test`, `world-test_nether`, `world-test_the_end`) for a fresh start.

### sync-to-test-server.ps1

Exports an `.mrpack` from the MCC packwiz project. The server will auto-update from packwiz serve on next start.

## Development Workflow

```
┌─────────────────────────────────────────────────────────────┐
│  1. Edit modpack in ../MCC/                                 │
│     - Add/remove mods: packwiz mr install <mod>             │
│     - Edit configs in overrides/                            │
├─────────────────────────────────────────────────────────────┤
│  2. Start packwiz serve                                     │
│     cd ../MCC && packwiz serve                              │
├─────────────────────────────────────────────────────────────┤
│  3. Start test server (auto-updates from packwiz)           │
│     start.bat                                               │
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

### Packwiz Issues

| Error | Solution |
|-------|----------|
| "Connection refused" on update | Ensure `packwiz serve` is running |
| Mods not updating | Run `packwiz refresh` in MCC directory |

## First-Time Setup

If setting up from scratch (JARs not present):

```powershell
# Download Fabric server launcher
Invoke-WebRequest -Uri "https://meta.fabricmc.net/v2/versions/loader/1.21.1/0.16.9/1.0.1/server/jar" -OutFile "fabric-server-launch.jar"

# Download packwiz-installer-bootstrap
Invoke-WebRequest -Uri "https://github.com/packwiz/packwiz-installer-bootstrap/releases/latest/download/packwiz-installer-bootstrap.jar" -OutFile "packwiz-installer-bootstrap.jar"
```

## Related Projects

| Repository | Purpose |
|------------|---------|
| [MCC](https://github.com/mindfulent/MCC) | Packwiz modpack source |
| [minecraftcollege](https://github.com/mindfulent/minecraftcollege) | Community website |

## License

MIT

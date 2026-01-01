# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This repository contains a local Minecraft 1.21.1 Fabric test server for Windows. It's used to validate MCC modpack changes before deploying to the production server on Bloom.host.

## Directory Structure

```
LocalServer/
├── docs/LOCAL-GUIDE.md.txt    # Comprehensive setup guide
├── scripts/                    # Automation scripts
│   ├── start-test-env.bat     # Launch entire test environment
│   ├── reset-test-world.bat   # Delete and regenerate test world
│   └── sync-to-test-server.ps1 # Export mrpack from MCC
├── start.bat                   # Main server launcher
├── start-with-restart.bat      # Auto-restart on crash
├── server.properties           # Server configuration
└── eula.txt                    # EULA acceptance
```

## Quick Start

```bash
# Terminal 1: Start packwiz serve
cd ../MCC && ./packwiz.exe serve

# Terminal 2: Start test server
./start.bat

# Or use all-in-one launcher:
./scripts/start-test-env.bat
```

Connect in Minecraft: `localhost:25565`

## Key Configuration

- **Java 21**: Uses Prism Launcher's bundled JDK at `%APPDATA%\PrismLauncher\java\java-runtime-delta\`
- **RAM**: 4GB allocated (adjustable in start.bat)
- **Packwiz Integration**: Auto-syncs mods from `http://localhost:8080/pack.toml` when packwiz serve is running
- **Offline Mode**: `online-mode=false` for faster testing

## Ports

| Service | Port |
|---------|------|
| Minecraft Server | 25565 |
| RCON | 25575 (pw: `testpassword`) |
| Packwiz Serve | 8080 |

## Related Projects

| Directory | Purpose |
|-----------|---------|
| `../MCC/` | Packwiz modpack source |

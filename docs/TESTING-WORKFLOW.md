# LocalServer Testing Workflow

This document describes the multi-mode testing workflow for LocalServer.

---

## Quick Reference

| Mode | Script | Use Case |
|------|--------|----------|
| Vanilla | `start-vanilla.bat` | Test without mods |
| Development | `start.bat` | Current packwiz workflow (superflat, peaceful) |
| Production | `scripts/production-mode.bat` | Replicate production experience |
| Version Testing | `scripts/test-version.bat` | Test specific version tags |
| Release Validation | `scripts/validate-release.ps1` | Test exact release artifact |

---

## Mode 1: Vanilla (No Mods)

Run a clean Fabric 1.21.1 server without modpack mods (Fabric API is preserved).

**Use cases:**
- Testing if an issue is mod-related vs. vanilla
- Performance baseline comparisons
- Testing Fabric API compatibility

**Usage:**
```batch
:: First, clear existing mods
scripts\clear-mods.bat

:: Start vanilla server
start-vanilla.bat
```

**Scripts:**
- `start-vanilla.bat` - Launches server without packwiz sync
- `scripts/clear-mods.bat` - Removes all mods except Fabric API

---

## Mode 2: Development (Current Workflow)

Test the latest development state of MCC. This is the default workflow.

**Use cases:**
- Testing new mods before adding to modpack
- Iterating on config changes
- Day-to-day development

**Usage:**
```batch
:: Terminal 1: Serve the modpack
cd ..\MCC
packwiz serve

:: Terminal 2: Start server (syncs from packwiz)
start.bat
```

Or use the all-in-one launcher:
```batch
scripts\start-test-env.bat
```

---

## Mode 3: Production Mode

Replicate the production server experience with normal world generation, mobs, and synced configs.

**Use cases:**
- Testing gameplay as players experience it
- Verifying mob spawning and world generation
- Testing production configs (Distant Horizons, etc.)

**Usage:**
```batch
:: Switch to production mode (syncs configs from MCC)
scripts\production-mode.bat

:: Start server
start.bat

:: When done, switch back to test mode
scripts\test-mode.bat
```

**What it does:**
1. Swaps `server.properties` to production settings
2. Syncs `config/` folder from MCC
3. Uses `world-production` (normal generation, not superflat)

**Key differences from test mode:**

| Setting | Test Mode | Production Mode |
|---------|-----------|-----------------|
| World type | Superflat | Normal |
| Difficulty | Peaceful | Normal |
| Mobs | Disabled | Enabled |
| View distance | 8 | 12 |
| Configs | LocalServer defaults | Synced from MCC |

**Scripts:**
- `scripts/production-mode.bat` - Switch to production settings
- `scripts/test-mode.bat` - Switch back to test settings

---

## Mode 4: Version Testing

Test a specific tagged version of MCC (e.g., v0.9.52). Can be combined with Production Mode.

**Use cases:**
- Reproducing bugs reported in a specific version
- Comparing behavior between versions
- Bisecting to find when a bug was introduced

**Usage:**
```batch
scripts\test-version.bat
```

The script will:
1. Stash uncommitted changes in MCC (if any)
2. Show available version tags
3. Checkout the selected tag
4. Start packwiz serve for that version
5. Start LocalServer

**After testing:**
```batch
:: Return to development branch
cd ..\MCC
git checkout main
git stash pop  :: if you stashed changes
```

---

## Mode 5: Release Validation

Test the exact `.mrpack` artifact that players download from GitHub releases.

**Use cases:**
- Final validation before announcing a release
- Testing what players actually experience
- Catching export/packaging bugs

**Usage:**
```powershell
# Run from LocalServer directory
.\scripts\validate-release.ps1

# Or specify version directly
.\scripts\validate-release.ps1 -Version v0.9.52
```

The script will:
1. Show recent GitHub releases
2. Download the mrpack from GitHub
3. Extract and install mods to LocalServer
4. Apply config overrides

**After extraction, start with:**
```batch
start-vanilla.bat
```

Use `start-vanilla.bat` (not `start.bat`) to prevent packwiz from overwriting the extracted mods.

---

## Workflow Recommendations

### Pre-Release Checklist

Before creating a new MCC release:

1. **Development testing**: Use Mode 2 to test your changes
2. **Version comparison**: Use Mode 3 if comparing to previous version
3. **Create the release**: Export mrpack, create GitHub release
4. **Validate artifact**: Use Mode 4 to test the actual mrpack
5. **Announce**: Post to Discord if validation passes

### Debugging a Reported Bug

1. Get the version number from the user
2. Use Mode 3 (`test-version.bat`) to checkout that version
3. Reproduce the bug
4. Compare with Mode 2 (latest dev) to see if already fixed

---

## File Reference

| File | Purpose |
|------|---------|
| `start.bat` | Development mode with packwiz sync |
| `start-vanilla.bat` | No packwiz sync, warns if mods present |
| `server.properties.test` | Test mode settings (superflat, peaceful) |
| `server.properties.production` | Production mode settings (normal world, mobs) |
| `scripts/production-mode.bat` | Switch to production settings + sync configs |
| `scripts/test-mode.bat` | Switch back to test settings |
| `scripts/clear-mods.bat` | Remove all mods except Fabric API |
| `scripts/test-version.bat` | Checkout MCC tag and serve |
| `scripts/validate-release.ps1` | Download and extract mrpack |
| `scripts/start-test-env.bat` | All-in-one dev environment launcher |
| `scripts/reset-test-world.bat` | Delete test world |

---

*See also: `docs/LOCAL-GUIDE.md.txt` for comprehensive setup instructions.*

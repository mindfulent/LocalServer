# Changelog

All notable changes to the LocalServer test environment will be documented in this file.

---

## [1.2.1] - 2026-01-01

### Fixed
- `scripts/validate-release.ps1` - Fixed mrpack extraction (rename to .zip for PowerShell compatibility)
- Updated `.gitignore` to exclude mod-generated folders (bluemap, config, journeymap, etc.)

### Changed
- Fabric Loader updated to 0.18.4 (required by newer mods)

---

## [1.2.0] - 2026-01-01

### Added
- **Production mode**: Replicate production server experience
  - `scripts/production-mode.bat` - Switch to production settings + sync configs from MCC
  - `scripts/test-mode.bat` - Switch back to test settings
  - `server.properties.production` - Normal world, mobs enabled, higher view distance
  - `server.properties.test` - Superflat, peaceful, optimized for quick testing
  - Syncs `config/` folder from MCC for production-like configs

---

## [1.1.0] - 2026-01-01

### Added
- Multi-mode testing workflow with four distinct modes:
  - **Vanilla mode**: `start-vanilla.bat` - Run server without modpack mods
  - **Development mode**: `start.bat` - Existing packwiz sync workflow
  - **Version testing**: `scripts/test-version.bat` - Test specific tagged versions
  - **Release validation**: `scripts/validate-release.ps1` - Validate mrpack artifacts
- `scripts/clear-mods.bat` - Remove all mods except Fabric API
- `docs/TESTING-WORKFLOW.md` - Documentation for all testing modes

---

## [1.0.0] - 2025-01-01

### Added
- Initial LocalServer setup for Minecraft 1.21.1 Fabric
- `start.bat` - Main server launcher with packwiz-installer integration
- `start-with-restart.bat` - Auto-restart on crash
- `scripts/start-test-env.bat` - All-in-one test environment launcher
- `scripts/reset-test-world.bat` - World reset utility
- `docs/LOCAL-GUIDE.md.txt` - Comprehensive setup guide
- Server configured for offline mode, flat world, creative gameplay
- RCON enabled on port 25575
- Auto-sync mods from packwiz serve on port 8080

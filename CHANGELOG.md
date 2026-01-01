# Changelog

All notable changes to the LocalServer test environment will be documented in this file.

---

## [Unreleased]

### Added
- `docs/TESTING-WORKFLOW-PLAN.md` - Plan for multi-mode testing workflow

### Planned
- Vanilla mode (`start-vanilla.bat`) - Run server without mods
- Version testing (`scripts/test-version.bat`) - Test specific modpack versions
- Release validation (`scripts/validate-release.ps1`) - Validate mrpack artifacts

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

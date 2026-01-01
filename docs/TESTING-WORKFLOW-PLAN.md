# LocalServer Testing Workflow Plan

This document outlines a proposed workflow for flexible testing scenarios with LocalServer.

---

## Goals

1. **Vanilla Mode**: Run a clean 1.21.1 Fabric server without any mods
2. **Version Testing**: Test specific modpack versions (e.g., v0.9.52) for bug reproduction
3. **Release Validation**: Verify that production `.mrpack` artifacts work correctly

---

## Current State

LocalServer currently uses `packwiz-installer-bootstrap.jar` in `start.bat` to auto-sync mods from `packwiz serve` running in `../MCC/`. This works well for testing the latest development state but doesn't support:

- Running without mods (vanilla)
- Testing a specific tagged version
- Validating the exact release artifact players download

---

## Proposed Workflow

### Mode 1: Vanilla (No Mods)

**Implementation**: Create `start-vanilla.bat` that bypasses packwiz-installer.

**Use cases**:
- Testing if an issue is mod-related vs. vanilla Minecraft
- Performance baseline comparisons
- Testing Fabric API compatibility

**Script behavior**:
1. Skip the `packwiz-installer-bootstrap.jar` step
2. Clear the `mods/` folder (except Fabric API if needed)
3. Launch server directly

**New files**:
- `start-vanilla.bat` - Server launcher without mod sync
- `scripts/clear-mods.bat` - Helper to clean mods folder

---

### Mode 2: Development Testing (Current)

**Implementation**: No changes needed - this is the existing workflow.

**Use cases**:
- Testing new mods before adding to modpack
- Iterating on config changes
- Day-to-day development

**Workflow**:
```
Terminal 1: cd ../MCC && packwiz serve
Terminal 2: ./start.bat
```

---

### Mode 3: Version Testing (Git Checkout)

**Implementation**: Use git tags in MCC repo to serve a specific version.

**Use cases**:
- Reproducing bugs reported in a specific version
- Comparing behavior between versions
- Bisecting to find when a bug was introduced

**Workflow**:
```bash
# 1. Stash or commit any current MCC work
cd ../MCC
git stash  # or git commit

# 2. Checkout the target version
git checkout v0.9.52

# 3. Serve that version
packwiz serve

# 4. Start LocalServer (syncs to v0.9.52)
cd ../LocalServer
./start.bat

# 5. Test...

# 6. Return to development branch
cd ../MCC
git checkout main
git stash pop  # if you stashed
```

**New files**:
- `scripts/test-version.bat` - Automates steps 1-4 (prompts for version tag)

**Considerations**:
- This temporarily switches MCC working directory
- Requires clean working tree (commit or stash first)
- Simple and uses existing infrastructure

---

### Mode 4: Release Validation (mrpack Install)

**Implementation**: Download and extract the exact `.mrpack` from GitHub releases.

**Use cases**:
- Final validation before announcing a release
- Testing what players actually download
- Catching export/packaging bugs

**Workflow**:
```bash
# 1. Download mrpack from GitHub release
# (manually or via script)

# 2. Clear existing mods
./scripts/clear-mods.bat

# 3. Extract mrpack to server
# Uses 7-Zip or built-in Windows unzip

# 4. Start server WITHOUT packwiz-installer
./start-vanilla.bat
```

**New files**:
- `scripts/validate-release.ps1` - Downloads mrpack from GitHub, extracts, launches server

**Why this matters**:
- Tests the exact artifact players receive
- Catches issues in the export process
- Catches missing files or incorrect paths in mrpack

---

## Proposed File Structure

```
LocalServer/
├── start.bat                    # Existing: dev mode with packwiz sync
├── start-vanilla.bat            # NEW: no mods, no packwiz
├── scripts/
│   ├── start-test-env.bat       # Existing
│   ├── reset-test-world.bat     # Existing
│   ├── clear-mods.bat           # NEW: removes all mods except Fabric API
│   ├── test-version.bat         # NEW: checkout tag + serve + start
│   └── validate-release.ps1     # NEW: download mrpack + extract + start
└── docs/
    ├── LOCAL-GUIDE.md.txt       # Existing comprehensive guide
    └── TESTING-WORKFLOW.md      # NEW: documents these workflows (final version of this plan)
```

---

## Implementation Tasks

### Phase 1: Vanilla Mode
- [ ] Create `start-vanilla.bat`
- [ ] Create `scripts/clear-mods.bat`
- [ ] Test vanilla server startup

### Phase 2: Version Testing
- [ ] Create `scripts/test-version.bat`
- [ ] Test with a known version tag (e.g., v0.9.52)
- [ ] Document git workflow in final docs

### Phase 3: Release Validation
- [ ] Create `scripts/validate-release.ps1`
- [ ] Test downloading and extracting an mrpack
- [ ] Verify server starts correctly with extracted mods

### Phase 4: Documentation
- [ ] Convert this plan to `docs/TESTING-WORKFLOW.md`
- [ ] Update `CLAUDE.md` with new workflow options
- [ ] Update `docs/LOCAL-GUIDE.md.txt` if needed

---

## Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vanilla mode implementation | Separate start script | Simple, no file manipulation needed |
| Fabric API in vanilla mode | Keep it | "Vanilla" means no major mods, not literally zero jars |
| Version testing | Git checkout in MCC | Uses existing infrastructure, infrequent need |
| Release validation | Download + extract mrpack | Tests exact production artifact |
| mrpack extraction | PowerShell Expand-Archive | Built-in, no dependencies |
| Mods folder backup | Don't backup | packwiz-installer regenerates everything anyway |

---

*This is a PLAN document. Implementation will proceed after approval.*

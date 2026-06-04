---
name: backup-vass
description: Backup and restore the VASS voice assistant application. Use ONLY when the user asks to backup, restore, save state, or archive the VASS project.
---

# Backup VASS

Creates a timestamped zip archive of all VASS source files and config, or restores from an existing backup.

## Files backed up

**Full project copy via robocopy (preserves folder structure):**
- All source code, config, scripts, locale files
- MCP server, allowed tools, VASScript examples
- Wakeword model, training samples (if present)

**Excluded:**
- `*.onnx`, `*.onnx.json` — Piper voice models (too large)
- `__pycache__/`, `bk/`, `.git/`, `.opencode/`
- Runtime logs: `vass.log`, `debug.log`, `crash.log`, `faulthandler.log`, MCP request log

## Commands

### Create backup

```
.scripts\backup.bat
```

Archive saved to `bk\vass_YYYYMMDD_HHMMSS.zip`.

### Restore from backup

List available backups:

```
Get-ChildItem -Path "bk" -Filter "*.zip" | Select-Object Name
```

Extract a specific backup over the current directory:

```
powershell -NoProfile -Command "Expand-Archive -Path 'bk\vass_20260523_170000.zip' -DestinationPath '.' -Force"
```

Always back up before making any destructive changes to the codebase.

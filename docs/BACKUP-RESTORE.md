# Backup & Restore Guide

This guide explains how to backup and restore your AI Memory Qdrant database.

## Overview

### What Gets Backed Up

- **3 Collections**: `discussions`, `conventions`, `code-patterns`
- **Configuration files**: `settings.json`, `.env` (from install directory)
- **Optional**: Log files (with `--include-logs` flag)

### Where Backups Are Stored

Backups are stored in `<repo>/backups/` by default:

```
ai-memory/
└── backups/
    └── 2026-02-03_143052/
        ├── qdrant/
        │   ├── discussions.snapshot
        │   ├── conventions.snapshot
        │   └── code-patterns.snapshot
        ├── config/
        │   ├── settings.json
        │   └── .env
        └── manifest.json
```

This location is **inside the repository directory** (not the install directory), so backups survive reinstallation.

### Manifest File

Each backup includes a `manifest.json` for verification:

```json
{
  "backup_date": "2026-02-03T14:30:52.123456+00:00",
  "ai_memory_version": "2.0.2",
  "qdrant_host": "localhost",
  "qdrant_port": 26350,
  "collections": {
    "discussions": {
      "name": "discussions",
      "records": 42,
      "snapshot_file": "discussions.snapshot",
      "size_bytes": 1048576
    }
  },
  "config_files": ["settings.json", ".env"],
  "includes_logs": false
}
```

---

## Prerequisites

- **Docker services running** (Qdrant must be accessible)
- **Python 3.10+**
- **httpx library** (not included in base requirements)

---

## Setup (One-Time)

### Step 1: Navigate to AI-Memory Repository

```bash
cd /path/to/ai-memory  # Where you cloned the repo
```

### Step 2: Create Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# OR
.venv\Scripts\activate     # Windows
```

### Step 3: Install Required Dependency

```bash
pip install httpx
```

### Step 4: Get Your QDRANT_API_KEY

Find the key in your installation's `.env` file:

```bash
cat ~/.ai-memory/docker/.env | grep QDRANT_API_KEY
```

Copy the value after the `=` sign (e.g., `QDRANT_API_KEY=abc123...`).

### Step 5: Export the Key

```bash
export QDRANT_API_KEY="your-key-here"
```

---

## Backup

### Basic Backup

```bash
python scripts/backup_qdrant.py
```

### Custom Output Directory

```bash
python scripts/backup_qdrant.py --output /custom/path
```

### Include Logs

```bash
python scripts/backup_qdrant.py --include-logs
```

### Expected Output

```
============================================================
  AI Memory Backup
============================================================

  Backup directory: /path/to/ai-memory/backups/2026-02-03_143052
  Qdrant: localhost:26350

  Checking disk space...
    ✓ 50.2 GB available
  Backing up discussions...
    ✓ 42 records, snapshot created (1.2 MB)
  Backing up conventions...
    ✓ 15 records, snapshot created (512.0 KB)
  Backing up code-patterns...
    ✓ 8 records, snapshot created (256.0 KB)

  Backing up config files...
    ✓ settings.json
    ✓ .env

============================================================
  ✓ Backup complete: /path/to/ai-memory/backups/2026-02-03_143052

  Total size: 2.0 MB
  Collections: 3
  Records: 65
============================================================
```

### Backup Contents

| Directory | Contents |
|-----------|----------|
| `qdrant/` | Collection snapshots (`.snapshot` files) |
| `config/` | Settings and `.env` backup |
| `logs/` | Log files (if `--include-logs` used) |
| `manifest.json` | Backup metadata for verification |

---

## Restore

### Basic Restore

```bash
python scripts/restore_qdrant.py backups/2026-02-03_143052
```

### Force Overwrite (No Confirmation)

```bash
python scripts/restore_qdrant.py backups/2026-02-03_143052 --force
```

### Restore Config Files Too

```bash
python scripts/restore_qdrant.py backups/2026-02-03_143052 --restore-config
```

### Restore Config with Force

```bash
python scripts/restore_qdrant.py backups/2026-02-03_143052 --restore-config --force
```

### Expected Output

```
============================================================
  AI Memory Restore
============================================================

  Backup: /path/to/ai-memory/backups/2026-02-03_143052

  Verifying backup...
    ✓ manifest.json valid
  Backup date: 2026-02-03 14:30:52
  Version: 2.0.2

    ✓ discussions.snapshot (1.2 MB)
    ✓ conventions.snapshot (512.0 KB)
    ✓ code-patterns.snapshot (256.0 KB)

  Connecting to Qdrant (localhost:26350)...
    ✓ Connected

  Restoring collections...
    Restoring discussions (42 records)...
      ✓ Snapshot uploaded
      ✓ Collection recovered
    Restoring conventions (15 records)...
      ✓ Snapshot uploaded
      ✓ Collection recovered
    Restoring code-patterns (8 records)...
      ✓ Snapshot uploaded
      ✓ Collection recovered

============================================================
  ✓ Restore complete

  Collections restored: 3
  Total records: 65
============================================================
```

---

## Verification

### Verify Backup Completed Successfully

1. Check the backup directory exists:
   ```bash
   ls -la backups/
   ```

2. Verify manifest.json is present and valid:
   ```bash
   cat backups/2026-02-03_143052/manifest.json | python -m json.tool
   ```

3. Verify all snapshot files exist:
   ```bash
   ls -la backups/2026-02-03_143052/qdrant/
   ```

### Verify Restore Completed Successfully

1. Check collection health via Qdrant API:
   ```bash
   curl -H "api-key: $QDRANT_API_KEY" http://localhost:26350/collections
   ```

2. Verify record counts match manifest:
   ```bash
   curl -H "api-key: $QDRANT_API_KEY" http://localhost:26350/collections/discussions
   ```

3. Test memory retrieval:
   ```bash
   /aim-status
   ```

---

## Troubleshooting

### HTTP 401 Unauthorized

**Cause**: `QDRANT_API_KEY` not set or incorrect.

**Solution**:
```bash
# Get the correct key from your installation
cat ~/.ai-memory/docker/.env | grep QDRANT_API_KEY

# Export it
export QDRANT_API_KEY="your-key-here"
```

### Connection Refused

**Cause**: Docker services not running.

**Solution**:
```bash
cd ~/.ai-memory/docker && docker compose up -d
```

### Snapshot Upload Timeout

**Cause**: Large collections taking too long to upload.

**Solution**: The default timeout is 5 minutes (`SNAPSHOT_UPLOAD_TIMEOUT=300`). For very large collections, you may need to modify the script or split the restore.

### Insufficient Disk Space (Exit Code 3)

**Cause**: Not enough space for backup files.

**Solution**: The backup script requires 2x the estimated backup size as safety margin. Free up disk space or specify a different output directory on a larger volume.

### Missing httpx Library

**Cause**: Required dependency not installed.

**Solution**:
```bash
pip install httpx
```

### Restore Rollback

If a restore fails mid-way, the script automatically rolls back any collections that were already restored. This prevents partial restore states.

---

## Best Practices

1. **Backup before major upgrades**
   ```bash
   python scripts/backup_qdrant.py
   ./scripts/upgrade.sh
   ```

2. **Store backups off-machine periodically**
   ```bash
   rsync -av backups/ backup-server:/ai-memory-backups/
   ```

3. **Test restore procedure on fresh install**
   - Spin up a test environment
   - Run restore with `--force`
   - Verify data integrity

4. **Automate backups** (optional)
   ```bash
   # Add to crontab for daily backups
   0 2 * * * cd /path/to/ai-memory && .venv/bin/python scripts/backup_qdrant.py
   ```

5. **Rotate old backups**
   ```bash
   # Keep last 7 days of backups
   find backups/ -maxdepth 1 -type d -mtime +7 -exec rm -rf {} \;
   ```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Qdrant connection failed |
| 2 | Collection backup failed |
| 3 | Insufficient disk space / Qdrant connection failed (restore) |
| 4 | Config backup failed / Collection restore failed |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QDRANT_HOST` | `localhost` | Qdrant server hostname |
| `QDRANT_PORT` | `26350` | Qdrant external port |
| `QDRANT_API_KEY` | (none) | API key for Qdrant authentication |
| `AI_MEMORY_BACKUP_DIR` | `<repo>/backups` | Default backup directory |
| `AI_MEMORY_INSTALL_DIR` | `~/.ai-memory` | Installation directory |

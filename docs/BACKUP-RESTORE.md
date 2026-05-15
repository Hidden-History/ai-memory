# Backup & Restore Guide

This guide explains how to backup and restore your AI Memory Qdrant database.

## Same-Version Restore Contract

`backup_qdrant.py` and `restore_qdrant.py` are a **same-version round-trip**
tool. They are designed for disaster recovery, dev clones, and pre-upgrade
safety snapshots — backing up a collection and restoring it to a collection
with an **identical schema**.

They are **not** a cross-version migration tool. If a release changes the
Qdrant collection schema (new vector type, new sparse config, etc.), that
release ships a dedicated `migrate_v<XXX>_*.py` script which is run once at
upgrade time. Restoring a backup whose schema differs from the live target
is refused with an actionable error rather than silently producing a broken
collection.

Each backup manifest records a **schema fingerprint** for every collection
(vector config, sparse config, multivector config, HNSW config, quantization
config, payload indexes). On restore:

- **Fresh install** (target collection absent) — the collection is recreated
  from the fingerprint with byte-equivalent structure, then the snapshot is
  recovered into it.
- **Existing target** — the live schema fingerprint is compared against the
  backup. A mismatch fails fast and points you at the per-version migrate
  script.
- **Legacy backup** (manifest predates v2.4.1, no fingerprint) — restore
  fails fast with guidance to provision collections via
  `scripts/setup-collections.py` first.

## Overview

### What Gets Backed Up

- **5 Collections**: `discussions`, `conventions`, `code-patterns`, `github`, `jira-data`
- **Schema fingerprint**: full vector / sparse / multivector / HNSW / quantization
  / payload-index configuration per collection, stored in the manifest
- **Configuration files**: `settings.json`, the legacy root `.env`, and the
  v2.4.0+ split env layout (`docker/.env` + `docker/.env.secrets`)
- **CHECKSUMS.sha256**: SHA-256 digests of the manifest and every snapshot file
- **Optional**: Log files (with `--include-logs` flag)

> **v2.4.1+ env file note**: The backup script now captures `docker/.env` and
> `docker/.env.secrets` automatically (in addition to the legacy root `.env`).
> `restore_qdrant.py --restore-config` restores both files and re-applies the
> `644`/`600` permission convention. Backups taken before v2.4.1 only contain
> the legacy root `.env`; if you are on v2.4.0 or restoring an older backup,
> back up and restore the split env files manually. See `docker/.env.example`,
> `docker/.env.secrets.example`, and `docs/CONFIGURATION.md` for the key list
> (BUG-277 / v2.4.0).

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
        │   ├── .env
        │   └── docker/
        │       ├── .env
        │       └── .env.secrets
        ├── manifest.json
        └── CHECKSUMS.sha256
```

This location is **inside the repository directory** (not the install directory), so backups survive reinstallation.

### Manifest File

Each backup includes a `manifest.json` for verification:

```json
{
  "backup_date": "2026-02-03T14:30:52.123456+00:00",
  "ai_memory_version": "2.4.1",
  "qdrant_host": "localhost",
  "qdrant_port": 26350,
  "collections": {
    "discussions": {
      "name": "discussions",
      "records": 42,
      "snapshot_file": "discussions.snapshot",
      "size_bytes": 1048576,
      "schema": {
        "params": { "vectors": {}, "sparse_vectors": {}, "shard_number": 1,
                    "on_disk_payload": true },
        "hnsw_config": {},
        "quantization_config": {},
        "payload_schema": {}
      }
    }
  },
  "config_files": ["settings.json", ".env", "docker/.env", "docker/.env.secrets"],
  "includes_logs": false,
  "runtime_flags": {
    "COLBERT_RERANKING_ENABLED": "true",
    "HYBRID_SEARCH_ENABLED": "false",
    "BM25_SPARSE_ENABLED": "true"
  }
}
```

The `schema` block per collection is the **schema fingerprint** the restore
path uses to recreate the collection (see the Same-Version Restore Contract
above). `runtime_flags` is diagnostic context only — it records which
embedding/search feature flags were active at backup time and is not used
for any restore decision.

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

### Single Collection

```bash
python scripts/backup_qdrant.py --collection discussions
```

### Retry Failed Downloads

Re-attempt a snapshot download on transient timeout (partial files are
discarded before each retry):

```bash
python scripts/backup_qdrant.py --retry 2
```

### Override Recorded Version

When `version.txt` is absent the manifest records `"unknown"` and a warning
is emitted. Supply the version explicitly:

```bash
python scripts/backup_qdrant.py --version 2.4.1
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

### Preview Without Changes (Dry Run)

```bash
python scripts/restore_qdrant.py backups/2026-02-03_143052 --dry-run
```

### Single Collection

```bash
python scripts/restore_qdrant.py backups/2026-02-03_143052 --collection discussions
```

### Restore Under a Different Name

Restore one collection into a staging name without touching the original —
useful for round-trip verification:

```bash
python scripts/restore_qdrant.py backups/2026-02-03_143052 \
  --collection discussions --target-name discussions_staging
```

`--target-name` requires `--collection`.

### Skip Checksum Verification

By default the restore verifies `CHECKSUMS.sha256` before uploading anything.
To bypass it (for example, on a filesystem prone to benign checksum drift):

```bash
python scripts/restore_qdrant.py backups/2026-02-03_143052 --skip-checksum-verify
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

If a restore fails mid-way, the script automatically rolls back:

- **Freshly created collections** (absent before the restore) are deleted.
- **Pre-existing collections** are recovered from a server-side snapshot
  taken automatically *before* the destructive restore began, returning them
  to exactly their pre-restore state.

This prevents partial restore states and protects existing data when a
restore over a populated collection fails.

### Schema Mismatch on `<collection>`

**Cause**: the backup's schema fingerprint differs from the live target
collection — typically a cross-version restore.

**Solution**: backup/restore is a same-version tool (see the Same-Version
Restore Contract above). Use the per-version `migrate_v<XXX>_*.py` script
that shipped with the release whose schema you are moving to.

### Manifest Predates v2.4.1

**Cause**: the backup was taken before v2.4.1 and has no schema fingerprint.

**Solution**: provision the collections first with
`python scripts/setup-collections.py`, then re-run the restore.

### Checksum Verification Failed

**Cause**: a snapshot file or the manifest no longer matches the digest
recorded in `CHECKSUMS.sha256` — the backup is corrupt or was modified.

**Solution**: use an intact backup. If the drift is known-benign (for
example, a filesystem quirk), re-run with `--skip-checksum-verify`.

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
| 1 | Qdrant connection failed (backup) / invalid arguments (restore) |
| 2 | Collection backup failed / backup verification failed / legacy manifest without schema fingerprint / checksum verification failed |
| 3 | Insufficient disk space / Qdrant connection failed (restore) |
| 4 | Config backup failed / collection restore failed (rollback performed) |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QDRANT_HOST` | `localhost` | Qdrant server hostname |
| `QDRANT_PORT` | `26350` | Qdrant external port |
| `QDRANT_API_KEY` | (none) | API key for Qdrant authentication |
| `AI_MEMORY_BACKUP_DIR` | `<repo>/backups` | Default backup directory |
| `AI_MEMORY_INSTALL_DIR` | `~/.ai-memory` | Installation directory |
| `BACKUP_SNAPSHOT_CREATE_TIMEOUT` | `300` | Snapshot-create timeout (seconds) |
| `BACKUP_SNAPSHOT_DOWNLOAD_TIMEOUT` | `300` | Snapshot-download timeout (seconds) |

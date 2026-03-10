#!/usr/bin/env python3
"""Generate Prometheus config files with fresh bcrypt hash.

BLK-021: prom/prometheus is BusyBox-based (no package manager, no Python).
This script runs in a python:3.12-alpine init container before Prometheus starts.
It generates web.yml (with bcrypt hash) and prometheus.yml (with env var substitution).

References:
  - DEC-072: Init container approach for BusyBox compatibility
  - BUG-210: Runtime bcrypt hash generation (fixes stale hash 401s)
  - Best practice: Docker init container pattern for config generation
"""

import os
import sys
import tempfile

import bcrypt


def atomic_write(path, content):
    """Write content atomically using temp file + rename."""
    dir_name = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(content)
        os.rename(tmp_path, path)
    except Exception:
        os.unlink(tmp_path)
        raise


def main():
    password = os.environ.get('PROMETHEUS_ADMIN_PASSWORD', '').strip()
    qdrant_key = os.environ.get('QDRANT_API_KEY', '').strip()

    if not password:
        print('ERROR: PROMETHEUS_ADMIN_PASSWORD not set', file=sys.stderr)
        sys.exit(1)
    if not qdrant_key:
        print('ERROR: QDRANT_API_KEY not set', file=sys.stderr)
        sys.exit(1)

    runtime_dir = '/etc/prometheus/runtime'
    os.makedirs(runtime_dir, exist_ok=True)

    # Clear stale configs to prevent prometheus from reading outdated files
    # if this init container fails after partial write
    for f in os.listdir(runtime_dir):
        os.remove(os.path.join(runtime_dir, f))

    # Generate bcrypt hash from current password
    hash_val = bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()
    assert hash_val.startswith('$2b$'), f'Unexpected bcrypt hash format: {hash_val[:10]}'

    # Generate web.yml with fresh bcrypt hash
    with open('/etc/prometheus/web.yml.template') as f:
        template = f.read()
    web_yml_path = os.path.join(runtime_dir, 'web.yml')
    atomic_write(web_yml_path, template.replace('${BCRYPT_HASH}', hash_val))
    print(f'web.yml generated (hash prefix: {hash_val[:20]}...)')

    # Generate prometheus.yml with env var substitution
    with open('/etc/prometheus/prometheus.yml.template') as f:
        prom = f.read()
    prom = prom.replace('${QDRANT_API_KEY}', qdrant_key)
    prom = prom.replace('${PROMETHEUS_ADMIN_PASSWORD}', password)
    prom_yml_path = os.path.join(runtime_dir, 'prometheus.yml')
    atomic_write(prom_yml_path, prom)
    print('prometheus.yml generated with env var substitution')


if __name__ == '__main__':
    main()

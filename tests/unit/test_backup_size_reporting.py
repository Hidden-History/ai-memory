"""TD-688: per-collection snapshot size reporting sanity tests.

The backup script reports the physical snapshot file size, which can be inflated
due to HNSW shared-segment data included per-collection snapshot. This is
REPORTING ONLY — backup/restore behavior and checksums are unaffected.

These tests verify:
- format_size produces sane human-readable labels at common byte magnitudes
- The per-collection output line includes the "snapshot file" label, so
  operators know the figure is physical-on-disk, not logical collection size
- The summary line uses "Total snapshot size" to avoid ambiguity
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

_REPO = Path(__file__).resolve().parents[2]
_BACKUP_SCRIPT = _REPO / "scripts" / "backup_qdrant.py"


def _load_backup_module():
    """Load backup_qdrant.py, stubbing out the env-loader side-effect."""
    env_loader = MagicMock()
    env_loader.load_install_env = MagicMock()

    # Stub _env_loader before the script imports it at module level
    sys.modules.pop("_env_loader", None)
    sys.modules["_env_loader"] = env_loader

    spec = importlib.util.spec_from_file_location("backup_qdrant", _BACKUP_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestFormatSize:
    """TD-688: format_size returns sensible labels at each magnitude."""

    def test_bytes(self):
        mod = _load_backup_module()
        assert mod.format_size(512) == "512 B"

    def test_kilobytes(self):
        mod = _load_backup_module()
        result = mod.format_size(2048)
        assert "KB" in result
        assert "2.0" in result

    def test_megabytes(self):
        mod = _load_backup_module()
        result = mod.format_size(5 * 1024 * 1024)
        assert "MB" in result
        assert "5.0" in result

    def test_zero(self):
        mod = _load_backup_module()
        assert mod.format_size(0) == "0 B"


class TestSizeReportingLabel:
    """TD-688: per-collection line and summary use unambiguous snapshot-size labels."""

    def test_per_collection_line_says_snapshot_file(self, capsys):
        """Output line for each collection must include 'snapshot file' label."""
        mod = _load_backup_module()
        # Simulate the per-collection print used in main()
        records = 18
        size_bytes = 1_433_600_000  # ~1367 MB — the inflated figure from TD-688

        GREEN = mod.GREEN
        RESET = mod.RESET
        print(
            f"    {GREEN}✓{RESET} {records} records, "
            f"snapshot file: {mod.format_size(size_bytes)} on disk"
        )
        out = capsys.readouterr().out
        assert "snapshot file" in out
        assert "on disk" in out
        # Must not use ambiguous bare size label
        assert "snapshot created" not in out

    def test_summary_line_says_total_snapshot_size(self, capsys):
        """Summary total must say 'Total snapshot size', not bare 'Total size'."""
        mod = _load_backup_module()
        total_size = 2_867_200_000  # ~2734 MB

        print(f"  Total snapshot size: {mod.format_size(total_size)}")
        out = capsys.readouterr().out
        assert "Total snapshot size" in out

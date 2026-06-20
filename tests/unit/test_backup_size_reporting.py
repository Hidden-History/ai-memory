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

    def _mock_main(self, mod, monkeypatch, tmp_path, size_bytes):
        """Patch all I/O helpers in *mod* and run main(), returning captured stdout."""
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "backup_qdrant.py",
                "--output",
                str(tmp_path),
                "--collection",
                "discussions",
            ],
        )
        mock_httpx = MagicMock()
        mock_httpx.get.return_value.status_code = 200
        monkeypatch.setattr(mod, "httpx", mock_httpx)
        monkeypatch.setattr(
            mod, "get_collection_info", lambda c: {"points_count": 18, "schema": None}
        )
        monkeypatch.setattr(
            mod, "check_disk_space", lambda bd, es: (True, 10 * 1024 * 1024 * 1024)
        )
        monkeypatch.setattr(mod, "create_snapshot", lambda c: f"{c}_snap")
        monkeypatch.setattr(
            mod, "download_snapshot", lambda c, s, o, retries=0: size_bytes
        )
        monkeypatch.setattr(mod, "delete_server_snapshot", lambda c, s: True)
        monkeypatch.setattr(mod, "backup_config_files", lambda bd: [])
        monkeypatch.setattr(mod, "create_manifest", lambda *a, **kw: None)
        monkeypatch.setattr(
            mod, "write_checksums", lambda bd: tmp_path / "CHECKSUMS.sha256"
        )
        return mod.main()

    def test_per_collection_line_says_snapshot_file(
        self, monkeypatch, capsys, tmp_path
    ):
        """main() per-collection output must include 'snapshot file' and 'on disk' labels."""
        mod = _load_backup_module()
        rc = self._mock_main(mod, monkeypatch, tmp_path, size_bytes=1_433_600_000)
        assert rc == 0
        out = capsys.readouterr().out
        assert "snapshot file" in out
        assert "on disk" in out
        assert "snapshot created" not in out

    def test_summary_line_says_total_snapshot_size(self, monkeypatch, capsys, tmp_path):
        """main() summary line must say 'Total snapshot size'."""
        mod = _load_backup_module()
        rc = self._mock_main(mod, monkeypatch, tmp_path, size_bytes=2_867_200_000)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Total snapshot size" in out

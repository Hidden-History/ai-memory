"""Unit tests for warn_if_workspace_stale (BP-161 / TD-522 workspace drift detection).

Function under test: warn_if_workspace_stale in sanctum_tier_b.py.
"""

import logging
import sys
from pathlib import Path

# Add the skill dir to sys.path so we can import the sibling module (Option P).
_SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SKILL_DIR))


def test_warn_if_workspace_stale_missing_stamp(tmp_path, caplog):
    """BP-161: missing .sync-stamp surfaces WARN log."""
    from sanctum_tier_b import warn_if_workspace_stale

    workspace = tmp_path / "ws"
    source = tmp_path / "src"
    workspace.mkdir()
    (source / ".git" / "refs" / "heads").mkdir(parents=True)
    (source / ".git" / "refs" / "heads" / "main").write_text("abc123\n")

    with caplog.at_level(logging.WARNING, logger="sanctum_tier_b"):
        warn_if_workspace_stale(workspace, source)

    assert any("workspace_sync_stamp_missing" in r.message for r in caplog.records)


def test_warn_if_workspace_stale_drift(tmp_path, caplog):
    """BP-161: stamp != source HEAD surfaces WARN log with both shas."""
    from sanctum_tier_b import warn_if_workspace_stale

    workspace = tmp_path / "ws"
    source = tmp_path / "src"
    workspace.mkdir()
    (source / ".git" / "refs" / "heads").mkdir(parents=True)
    (source / ".git" / "refs" / "heads" / "main").write_text("def456\n")
    (workspace / ".sync-stamp").write_text("abc123\n")

    with caplog.at_level(logging.WARNING, logger="sanctum_tier_b"):
        warn_if_workspace_stale(workspace, source)

    msgs = [r.message for r in caplog.records]
    assert any("workspace_sync_stale" in m for m in msgs)


def test_warn_if_workspace_stale_in_sync(tmp_path, caplog):
    """BP-161: matching stamp/HEAD emits no WARN."""
    from sanctum_tier_b import warn_if_workspace_stale

    workspace = tmp_path / "ws"
    source = tmp_path / "src"
    workspace.mkdir()
    (source / ".git" / "refs" / "heads").mkdir(parents=True)
    sha = "abc123def456"
    (source / ".git" / "refs" / "heads" / "main").write_text(sha + "\n")
    (workspace / ".sync-stamp").write_text(sha + "\n")

    with caplog.at_level(logging.WARNING, logger="sanctum_tier_b"):
        warn_if_workspace_stale(workspace, source)

    assert not any("workspace_sync_stale" in r.message for r in caplog.records)
    assert not any("workspace_sync_stamp_missing" in r.message for r in caplog.records)

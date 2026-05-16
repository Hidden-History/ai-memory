"""
Regression tests for per-instance sanctum preservation on installer Option 1 updates.

Covers two integration surfaces:
  1. Python helper _merge_sanctum_creed_frontmatter (R3, CREED frontmatter merge) —
     tested directly via import. No bash required; passes immediately after C1.
  2. deploy_parzival_v2() bash function (R1/R2/R4, backup/restore flow) — tested via
     bash subprocess that sources install.sh (minus final main call) with mocked env
     vars and overridden SCRIPT_DIR. These tests pass after install.sh C2-C5 edits land.

Per-instance preservation policy (parzival-answers.md DQ-1):
  LORE.md, BOND.md, sessions/*, capabilities/*, references/* are NOT in source template
  and must be preserved verbatim across Option 1 updates.

CREED.md policy (parzival-answers.md DQ-3 (a)):
  Body replaced from new template. Fields sessions_completed, last_session, updated,
  tier_promoted_on preserved from backup. Static fields (type, agent, domain, created-by,
  load, tier) come from new template.
"""

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from _merge_sanctum_creed_frontmatter import (
    FIELDS_TO_PRESERVE,
    _extract_field,
    _replace_field,
    _split_frontmatter,
    merge_creed_frontmatter,
)

# ---------------------------------------------------------------------------
# Shared CREED fixture content
# ---------------------------------------------------------------------------

_CREED_TEMPLATE = """\
---
type: sanctum-creed
agent: parzival
domain: project-orchestration
created-by: user
updated: null
load: activation
tier: 3
sessions_completed: 0
last_session: null
tier_promoted_on: null
---

# Creed

## Mission

Parzival is the radar, map reader, and navigator. The user is the captain.

---

## Core Values

- Quality over speed.
- Verification is concrete, not vibes-based.
"""

# Backup CREED: accumulated per-instance frontmatter + intentionally different
# static field 'tier: 2' (to verify static fields are NOT preserved from backup).
_CREED_BACKUP = """\
---
type: sanctum-creed
agent: parzival
domain: project-orchestration
created-by: user
updated: "2026-04-25T15:30:00Z"
load: activation
tier: 2
sessions_completed: 5
last_session: "2026-04-20T10:00:00Z"
tier_promoted_on: null
---

# Creed (old body — should be replaced by new template body)

## Mission

This body content should be replaced by the new template body after merge.
"""

# ---------------------------------------------------------------------------
# Class 1: Python helper unit tests (pass immediately after C1)
# ---------------------------------------------------------------------------


class TestSplitFrontmatter:
    def test_valid_frontmatter(self):
        fm, body = _split_frontmatter(_CREED_TEMPLATE)
        assert "sessions_completed: 0" in fm
        assert "# Creed" in body

    def test_no_frontmatter_returns_none(self):
        assert _split_frontmatter("# No frontmatter\n") is None

    def test_frontmatter_without_close_returns_none(self):
        assert _split_frontmatter("---\nkey: val\n") is None


class TestExtractField:
    def test_integer_field(self):
        fm, _ = _split_frontmatter(_CREED_BACKUP)
        assert _extract_field(fm, "sessions_completed") == "5"

    def test_quoted_string_field(self):
        fm, _ = _split_frontmatter(_CREED_BACKUP)
        assert _extract_field(fm, "last_session") == '"2026-04-20T10:00:00Z"'

    def test_null_field(self):
        fm, _ = _split_frontmatter(_CREED_BACKUP)
        assert _extract_field(fm, "tier_promoted_on") == "null"

    def test_missing_field_returns_none(self):
        fm, _ = _split_frontmatter(_CREED_BACKUP)
        assert _extract_field(fm, "nonexistent_field") is None


class TestReplaceField:
    def test_replaces_integer(self):
        fm, _ = _split_frontmatter(_CREED_TEMPLATE)
        result = _replace_field(fm, "sessions_completed", "5")
        assert "sessions_completed: 5" in result
        assert "sessions_completed: 0" not in result

    def test_replaces_null_with_string(self):
        fm, _ = _split_frontmatter(_CREED_TEMPLATE)
        result = _replace_field(fm, "last_session", '"2026-04-20T10:00:00Z"')
        assert 'last_session: "2026-04-20T10:00:00Z"' in result
        assert "last_session: null" not in result

    def test_preserves_other_fields(self):
        fm, _ = _split_frontmatter(_CREED_TEMPLATE)
        result = _replace_field(fm, "sessions_completed", "5")
        assert "type: sanctum-creed" in result
        assert "tier: 3" in result


class TestMergeCreedFrontmatter:
    @pytest.fixture
    def creed_dirs(self, tmp_path):
        backup_creed = tmp_path / "backup_CREED.md"
        target_creed = tmp_path / "target_CREED.md"
        backup_creed.write_text(_CREED_BACKUP, encoding="utf-8")
        target_creed.write_text(_CREED_TEMPLATE, encoding="utf-8")
        return backup_creed, target_creed

    def test_sessions_completed_preserved(self, creed_dirs):
        backup, target = creed_dirs
        merge_creed_frontmatter(backup, target)
        content = target.read_text()
        fm, _ = _split_frontmatter(content)
        assert _extract_field(fm, "sessions_completed") == "5"

    def test_last_session_preserved(self, creed_dirs):
        backup, target = creed_dirs
        merge_creed_frontmatter(backup, target)
        content = target.read_text()
        fm, _ = _split_frontmatter(content)
        assert _extract_field(fm, "last_session") == '"2026-04-20T10:00:00Z"'

    def test_updated_preserved(self, creed_dirs):
        backup, target = creed_dirs
        merge_creed_frontmatter(backup, target)
        content = target.read_text()
        fm, _ = _split_frontmatter(content)
        assert _extract_field(fm, "updated") == '"2026-04-25T15:30:00Z"'

    def test_tier_promoted_on_null_preserved(self, creed_dirs):
        backup, target = creed_dirs
        merge_creed_frontmatter(backup, target)
        content = target.read_text()
        fm, _ = _split_frontmatter(content)
        assert _extract_field(fm, "tier_promoted_on") == "null"

    def test_static_fields_from_new_template(self, creed_dirs):
        backup, target = creed_dirs
        merge_creed_frontmatter(backup, target)
        content = target.read_text()
        fm, _ = _split_frontmatter(content)
        # tier in backup is 2; template has tier: 3 — template value wins
        assert _extract_field(fm, "tier") == "3"
        assert _extract_field(fm, "type") == "sanctum-creed"
        assert _extract_field(fm, "agent") == "parzival"
        assert _extract_field(fm, "domain") == "project-orchestration"
        assert _extract_field(fm, "created-by") == "user"
        assert _extract_field(fm, "load") == "activation"

    def test_body_from_new_template(self, creed_dirs):
        backup, target = creed_dirs
        merge_creed_frontmatter(backup, target)
        content = target.read_text()
        _, body = _split_frontmatter(content)
        assert "Parzival is the radar, map reader, and navigator." in body
        assert "This body content should be replaced" not in body

    def test_missing_field_in_backup_skipped(self, tmp_path):
        backup_no_updated = _CREED_BACKUP.replace(
            'updated: "2026-04-25T15:30:00Z"\n', ""
        )
        backup = tmp_path / "backup.md"
        target = tmp_path / "target.md"
        backup.write_text(backup_no_updated, encoding="utf-8")
        target.write_text(_CREED_TEMPLATE, encoding="utf-8")
        merge_creed_frontmatter(backup, target)
        content = target.read_text()
        fm, _ = _split_frontmatter(content)
        # 'updated' missing from backup → target keeps its template value (null)
        assert _extract_field(fm, "updated") == "null"
        # Other preserved fields still merged
        assert _extract_field(fm, "sessions_completed") == "5"

    def test_no_backup_frontmatter_is_noop(self, tmp_path):
        backup = tmp_path / "backup.md"
        target = tmp_path / "target.md"
        backup.write_text("# No frontmatter here\n", encoding="utf-8")
        target.write_text(_CREED_TEMPLATE, encoding="utf-8")
        original_content = _CREED_TEMPLATE
        merge_creed_frontmatter(backup, target)
        assert target.read_text() == original_content

    def test_atomic_write_leaves_no_temp_files(self, creed_dirs):
        backup, target = creed_dirs
        before = set(target.parent.iterdir())
        merge_creed_frontmatter(backup, target)
        after = set(target.parent.iterdir())
        new_files = after - before
        assert all(".creed_merge_tmp_" not in f.name for f in new_files)

    def test_fields_to_preserve_constant(self):
        assert "sessions_completed" in FIELDS_TO_PRESERVE
        assert "last_session" in FIELDS_TO_PRESERVE
        assert "updated" in FIELDS_TO_PRESERVE
        assert "tier_promoted_on" in FIELDS_TO_PRESERVE
        assert "type" not in FIELDS_TO_PRESERVE
        assert "tier" not in FIELDS_TO_PRESERVE


# ---------------------------------------------------------------------------
# Class 2: Bash subprocess integration tests for deploy_parzival_v2()
# Tests pass after install.sh C2-C5 edits (sanctum backup/restore logic) land.
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"


@pytest.fixture
def install_sh_no_main(tmp_path) -> Path:
    """Copy install.sh minus final 'main "$@"' line into tmp_path for safe sourcing."""
    content = _INSTALL_SH.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    assert lines[-1].strip() == 'main "$@"', (
        f"Expected last line 'main \"$@\"', got: {lines[-1]!r}. "
        "If install.sh structure changed, update this fixture."
    )
    copy = tmp_path / "install.sh"
    copy.write_text("".join(lines[:-1]), encoding="utf-8")
    copy.chmod(0o755)
    shutil.copy(
        _SCRIPTS_DIR / "_env_split_helpers.sh", tmp_path / "_env_split_helpers.sh"
    )
    return copy


@pytest.fixture
def sanctum_install_dirs(tmp_path):
    """Create mock install dir (source template) and project dir (existing install).

    install_dir/_ai-memory/ — what the installer copies FROM (template + CREED base)
    project_dir/_ai-memory/ — existing user install (LORE/BOND/sessions + accumulated CREED)
    """
    install_dir = tmp_path / "install_dir"
    project_dir = tmp_path / "project_dir"

    # Source template: ships CREED.md (base) + 3 .gitkeep placeholders
    src_sanctum = install_dir / "_ai-memory" / "sanctum" / "parzival"
    src_sanctum.mkdir(parents=True)
    (src_sanctum / "CREED.md").write_text(_CREED_TEMPLATE, encoding="utf-8")
    for sub in ("sessions", "capabilities", "references"):
        (src_sanctum / sub).mkdir()
        (src_sanctum / sub / ".gitkeep").write_text("", encoding="utf-8")

    # Existing install: per-instance content
    dst_sanctum = project_dir / "_ai-memory" / "sanctum" / "parzival"
    dst_sanctum.mkdir(parents=True)
    (dst_sanctum / "CREED.md").write_text(_CREED_BACKUP, encoding="utf-8")
    (dst_sanctum / "LORE.md").write_text("test lore content", encoding="utf-8")
    (dst_sanctum / "BOND.md").write_text("test bond content", encoding="utf-8")
    (dst_sanctum / "sessions").mkdir()
    (dst_sanctum / "sessions" / "2026-04-20-test.md").write_text(
        "test session", encoding="utf-8"
    )

    return install_dir, project_dir


def _run_deploy_parzival_v2(
    install_sh_copy: Path,
    install_dir: Path,
    project_dir: Path,
) -> subprocess.CompletedProcess:
    """Source install.sh (no-main copy) and call deploy_parzival_v2 with mocked dirs.

    SCRIPT_DIR is overridden after source to point to the real scripts/ directory so
    that python3 "$SCRIPT_DIR/_merge_sanctum_creed_frontmatter.py" resolves correctly.
    """
    bash_cmd = f"""
set -euo pipefail
export INSTALL_DIR="{install_dir}"
export PROJECT_PATH="{project_dir}"
source "{install_sh_copy}"
INSTALL_DIR="{install_dir}"
PROJECT_PATH="{project_dir}"
SCRIPT_DIR="{_SCRIPTS_DIR}"
deploy_parzival_v2
"""
    return subprocess.run(
        ["bash", "-c", bash_cmd],
        capture_output=True,
        text=True,
    )


class TestDeployParzivalV2SanctumPreservation:
    """Bash subprocess smoke tests for deploy_parzival_v2() sanctum preservation.

    Require install.sh C2-C5 edits (sanctum backup/restore + CREED merge invocation).
    Will fail on the current install.sh (before those edits). Expected to be red
    until C2-C5 lands, then green by C7/C8.
    """

    def test_lore_preserved_exactly(self, install_sh_no_main, sanctum_install_dirs):
        install_dir, project_dir = sanctum_install_dirs
        result = _run_deploy_parzival_v2(install_sh_no_main, install_dir, project_dir)
        assert result.returncode == 0, f"deploy_parzival_v2 failed:\n{result.stderr}"
        lore = (
            project_dir / "_ai-memory" / "sanctum" / "parzival" / "LORE.md"
        ).read_text()
        assert lore == "test lore content"

    def test_bond_preserved_exactly(self, install_sh_no_main, sanctum_install_dirs):
        install_dir, project_dir = sanctum_install_dirs
        result = _run_deploy_parzival_v2(install_sh_no_main, install_dir, project_dir)
        assert result.returncode == 0, f"deploy_parzival_v2 failed:\n{result.stderr}"
        bond = (
            project_dir / "_ai-memory" / "sanctum" / "parzival" / "BOND.md"
        ).read_text()
        assert bond == "test bond content"

    def test_session_file_preserved(self, install_sh_no_main, sanctum_install_dirs):
        install_dir, project_dir = sanctum_install_dirs
        result = _run_deploy_parzival_v2(install_sh_no_main, install_dir, project_dir)
        assert result.returncode == 0, f"deploy_parzival_v2 failed:\n{result.stderr}"
        session = (
            project_dir
            / "_ai-memory"
            / "sanctum"
            / "parzival"
            / "sessions"
            / "2026-04-20-test.md"
        ).read_text()
        assert session == "test session"

    def test_creed_sessions_completed_preserved(
        self, install_sh_no_main, sanctum_install_dirs
    ):
        install_dir, project_dir = sanctum_install_dirs
        result = _run_deploy_parzival_v2(install_sh_no_main, install_dir, project_dir)
        assert result.returncode == 0, f"deploy_parzival_v2 failed:\n{result.stderr}"
        creed = (
            project_dir / "_ai-memory" / "sanctum" / "parzival" / "CREED.md"
        ).read_text()
        fm, _ = _split_frontmatter(creed)
        assert _extract_field(fm, "sessions_completed") == "5"

    def test_creed_last_session_preserved(
        self, install_sh_no_main, sanctum_install_dirs
    ):
        install_dir, project_dir = sanctum_install_dirs
        result = _run_deploy_parzival_v2(install_sh_no_main, install_dir, project_dir)
        assert result.returncode == 0, f"deploy_parzival_v2 failed:\n{result.stderr}"
        creed = (
            project_dir / "_ai-memory" / "sanctum" / "parzival" / "CREED.md"
        ).read_text()
        fm, _ = _split_frontmatter(creed)
        assert _extract_field(fm, "last_session") == '"2026-04-20T10:00:00Z"'

    def test_creed_updated_preserved(self, install_sh_no_main, sanctum_install_dirs):
        install_dir, project_dir = sanctum_install_dirs
        result = _run_deploy_parzival_v2(install_sh_no_main, install_dir, project_dir)
        assert result.returncode == 0, f"deploy_parzival_v2 failed:\n{result.stderr}"
        creed = (
            project_dir / "_ai-memory" / "sanctum" / "parzival" / "CREED.md"
        ).read_text()
        fm, _ = _split_frontmatter(creed)
        assert _extract_field(fm, "updated") == '"2026-04-25T15:30:00Z"'

    def test_creed_tier_promoted_on_null_preserved(
        self, install_sh_no_main, sanctum_install_dirs
    ):
        install_dir, project_dir = sanctum_install_dirs
        result = _run_deploy_parzival_v2(install_sh_no_main, install_dir, project_dir)
        assert result.returncode == 0, f"deploy_parzival_v2 failed:\n{result.stderr}"
        creed = (
            project_dir / "_ai-memory" / "sanctum" / "parzival" / "CREED.md"
        ).read_text()
        fm, _ = _split_frontmatter(creed)
        assert _extract_field(fm, "tier_promoted_on") == "null"

    def test_creed_static_fields_from_new_template(
        self, install_sh_no_main, sanctum_install_dirs
    ):
        install_dir, project_dir = sanctum_install_dirs
        result = _run_deploy_parzival_v2(install_sh_no_main, install_dir, project_dir)
        assert result.returncode == 0, f"deploy_parzival_v2 failed:\n{result.stderr}"
        creed = (
            project_dir / "_ai-memory" / "sanctum" / "parzival" / "CREED.md"
        ).read_text()
        fm, _ = _split_frontmatter(creed)
        # tier: 2 in backup; tier: 3 in template — template wins (static descriptor)
        assert _extract_field(fm, "tier") == "3"
        assert _extract_field(fm, "type") == "sanctum-creed"
        assert _extract_field(fm, "agent") == "parzival"
        assert _extract_field(fm, "load") == "activation"

    def test_creed_body_from_new_template(
        self, install_sh_no_main, sanctum_install_dirs
    ):
        install_dir, project_dir = sanctum_install_dirs
        result = _run_deploy_parzival_v2(install_sh_no_main, install_dir, project_dir)
        assert result.returncode == 0, f"deploy_parzival_v2 failed:\n{result.stderr}"
        creed = (
            project_dir / "_ai-memory" / "sanctum" / "parzival" / "CREED.md"
        ).read_text()
        _, body = _split_frontmatter(creed)
        assert "Parzival is the radar, map reader, and navigator." in body
        assert "This body content should be replaced" not in body

    def test_no_sanctum_dir_first_install_succeeds(self, install_sh_no_main, tmp_path):
        """R6: first-install scenario (no existing sanctum/) completes without error."""
        install_dir = tmp_path / "install_dir"
        project_dir = tmp_path / "project_dir"

        src_sanctum = install_dir / "_ai-memory" / "sanctum" / "parzival"
        src_sanctum.mkdir(parents=True)
        (src_sanctum / "CREED.md").write_text(_CREED_TEMPLATE, encoding="utf-8")
        for sub in ("sessions", "capabilities", "references"):
            (src_sanctum / sub).mkdir()
            (src_sanctum / sub / ".gitkeep").write_text("", encoding="utf-8")

        # project_dir has NO existing _ai-memory (first install)
        project_dir.mkdir()

        result = _run_deploy_parzival_v2(install_sh_no_main, install_dir, project_dir)
        assert result.returncode == 0, f"First-install failed:\n{result.stderr}"
        assert (
            project_dir / "_ai-memory" / "sanctum" / "parzival" / "CREED.md"
        ).exists()

    def test_no_sanctum_backup_dir_left_after_update(
        self, install_sh_no_main, sanctum_install_dirs
    ):
        """R4: sanctum_backup cleanup — no .parzival-sanctum-backup-* dirs remain."""
        install_dir, project_dir = sanctum_install_dirs
        result = _run_deploy_parzival_v2(install_sh_no_main, install_dir, project_dir)
        assert result.returncode == 0, f"deploy_parzival_v2 failed:\n{result.stderr}"
        leftover = list(install_dir.glob(".parzival-sanctum-backup-*"))
        assert leftover == [], f"Sanctum backup dirs not cleaned up: {leftover}"

    def test_creed_merge_failure_falls_back_to_backup(
        self, install_sh_no_main, sanctum_install_dirs, tmp_path
    ):
        """F-M2: on CREED merge helper failure, backup CREED.md is restored verbatim.

        Verifies that when CREED_MERGE_SCRIPT exits non-zero, deploy_parzival_v2
        still exits 0 (install continues) and the dst CREED.md is replaced by the
        user's backup content (cp-fallback), preserving per-instance identity.
        """
        install_dir, project_dir = sanctum_install_dirs

        broken_script = tmp_path / "broken_merge.sh"
        broken_script.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        broken_script.chmod(0o755)

        bash_cmd = f"""
set -euo pipefail
export INSTALL_DIR="{install_dir}"
export PROJECT_PATH="{project_dir}"
export CREED_MERGE_SCRIPT="{broken_script}"
source "{install_sh_no_main}"
INSTALL_DIR="{install_dir}"
PROJECT_PATH="{project_dir}"
SCRIPT_DIR="{_SCRIPTS_DIR}"
deploy_parzival_v2
"""
        result = subprocess.run(
            ["bash", "-c", bash_cmd],
            capture_output=True,
            text=True,
        )
        assert (
            result.returncode == 0
        ), f"deploy_parzival_v2 must not abort on CREED merge failure:\n{result.stderr}"
        creed = project_dir / "_ai-memory" / "sanctum" / "parzival" / "CREED.md"
        assert creed.exists(), "CREED.md must exist after install"
        creed_content = creed.read_text(encoding="utf-8")
        assert (
            "sessions_completed: 5" in creed_content
        ), "cp-fallback should restore backup CREED.md verbatim (sessions_completed: 5)"


# ---------------------------------------------------------------------------
# Class 3: mtime preservation regression (BUG-299 / F1)
# ---------------------------------------------------------------------------


class TestDeployParzivalV2MtimePreservation:
    """Regression for BUG-299: user files under _memory/ retain original mtime on reinstall.

    Requires install.sh to restore _memory/ user files with `cp -p` (BUG-299 fix).
    Without `cp -p` the restored file's mtime is the time of the install run, not
    the original — breaking `stat` / `find -newer` audit checks across reinstalls.
    """

    def test_memory_user_file_mtime_preserved(
        self, install_sh_no_main, sanctum_install_dirs
    ):
        """V2→V2 reinstall must preserve mtime for user-created _memory/ files.

        Sets up a pre-existing user file with a known mtime 24 hours in the past,
        runs deploy_parzival_v2, and asserts the restored file's mtime matches the
        original. Fails when install.sh uses `cp` without `-p` for _memory/ restore.
        """
        install_dir, project_dir = sanctum_install_dirs

        # Create a user-created file under _memory/ (not present in source template)
        memory_dir = project_dir / "_ai-memory" / "_memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        user_file = memory_dir / "user-note.md"
        user_file.write_text("user note content — mtime sentinel", encoding="utf-8")

        # Pin mtime to 24 h ago so it is clearly distinct from "now"
        original_mtime = time.time() - 86400
        os.utime(str(user_file), (original_mtime, original_mtime))

        result = _run_deploy_parzival_v2(install_sh_no_main, install_dir, project_dir)
        assert result.returncode == 0, f"deploy_parzival_v2 failed:\n{result.stderr}"

        restored_file = project_dir / "_ai-memory" / "_memory" / "user-note.md"
        assert restored_file.exists(), "_memory/user-note.md was not restored"
        assert (
            restored_file.read_text(encoding="utf-8")
            == "user note content — mtime sentinel"
        )

        restored_mtime = restored_file.stat().st_mtime

        # mtime must match original (within 2-second tolerance for filesystem precision).
        # Without `cp -p`, restored_mtime would be approximately now (>> original_mtime).
        assert abs(restored_mtime - original_mtime) < 2, (
            f"_memory/ user file mtime not preserved across reinstall: "
            f"original={original_mtime:.1f}, restored={restored_mtime:.1f} "
            f"(delta={abs(restored_mtime - original_mtime):.1f}s). "
            "Ensure install.sh restores _memory/ user files with `cp -p`."
        )

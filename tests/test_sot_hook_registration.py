"""Tests for SOT hook auto-registration on install (capability A, TASK-075a Phase-2).

Covers:
- Claude (generate_settings.py): SOT digest → SessionStart, SOT drift → Stop
- Gemini / Cursor / Codex (install.sh write_*_config): digest + drift per CLI
- Opt-out: AI_MEMORY_SOT_HOOKS=off skips registration for all CLIs
- Claude re-merge idempotency: no duplicate entries after a second merge

All tests are mocked / subprocess-based; no live services required.
AI_MEMORY_PROJECT_ID is intentionally unset.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).parent.parent
_SCRIPTS_DIR = _REPO / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"

# ---------------------------------------------------------------------------
# Helpers for install.sh subprocess tests
# ---------------------------------------------------------------------------


@pytest.fixture
def install_sh_no_main(tmp_path) -> Path:
    """Copy install.sh minus final 'main \"$@\"' line for safe sourcing."""
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
def install_dir(tmp_path) -> Path:
    """Minimal mock INSTALL_DIR (path strings only; no files required by write_*_config)."""
    d = tmp_path / "install_dir"
    d.mkdir()
    return d


def _call(
    install_sh: Path,
    func: str,
    project: Path,
    install: Path,
    force: str = "false",
    extra_env: dict | None = None,
) -> subprocess.CompletedProcess:
    bash_cmd = f"""
set -euo pipefail
source "{install_sh}"
{func} "{project}" "{install}" "test-project" "{force}"
"""
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", "-c", bash_cmd], capture_output=True, text=True, env=env
    )


# ---------------------------------------------------------------------------
# Claude — generate_settings.py
# ---------------------------------------------------------------------------


class TestClaudeSotRegistration:
    def test_digest_registered_in_session_start(self, monkeypatch):
        """SOT digest hook is registered in SessionStart by default (gate ON)."""
        from generate_settings import generate_hook_config

        monkeypatch.delenv("AI_MEMORY_SOT_HOOKS", raising=False)

        config = generate_hook_config("/test/hooks", "test-project")
        session_start = config["hooks"]["SessionStart"]

        commands = [h["command"] for w in session_start for h in w.get("hooks", [])]
        assert any(
            "sot_digest_session_start.py" in cmd for cmd in commands
        ), "sot_digest_session_start.py must appear in SessionStart hooks"

    def test_digest_matcher_is_resume_compact(self, monkeypatch):
        """SOT digest SessionStart wrapper uses resume|compact matcher (DEC-054/055)."""
        from generate_settings import generate_hook_config

        monkeypatch.delenv("AI_MEMORY_SOT_HOOKS", raising=False)

        config = generate_hook_config("/test/hooks", "test-project")
        session_start = config["hooks"]["SessionStart"]

        sot_wrappers = [
            w
            for w in session_start
            if any(
                "sot_digest_session_start.py" in h.get("command", "")
                for h in w.get("hooks", [])
            )
        ]
        assert sot_wrappers, "No SOT digest wrapper found in SessionStart"
        assert (
            sot_wrappers[0]["matcher"] == "resume|compact"
        ), "SOT digest matcher must be resume|compact"

    def test_drift_registered_in_stop(self, monkeypatch):
        """SOT drift hook is registered in Stop by default (gate ON)."""
        from generate_settings import generate_hook_config

        monkeypatch.delenv("AI_MEMORY_SOT_HOOKS", raising=False)
        monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)

        config = generate_hook_config("/test/hooks", "test-project")
        stop = config["hooks"]["Stop"]

        commands = [h["command"] for w in stop for h in w.get("hooks", [])]
        assert any(
            "sot_drift_stop.py" in cmd for cmd in commands
        ), "sot_drift_stop.py must appear in Stop hooks"

    def test_hooks_absent_when_gate_off(self, monkeypatch):
        """No SOT hooks registered when AI_MEMORY_SOT_HOOKS=off."""
        from generate_settings import generate_hook_config

        monkeypatch.setenv("AI_MEMORY_SOT_HOOKS", "off")
        monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)

        config = generate_hook_config("/test/hooks", "test-project")

        all_commands = [
            h["command"]
            for hook_list in config["hooks"].values()
            for w in hook_list
            for h in w.get("hooks", [])
        ]
        assert not any(
            "sot_digest_session_start.py" in cmd for cmd in all_commands
        ), "sot_digest_session_start.py must NOT be registered when gate is off"
        assert not any(
            "sot_drift_stop.py" in cmd for cmd in all_commands
        ), "sot_drift_stop.py must NOT be registered when gate is off"

    def test_remerge_no_duplicate_session_start(self, monkeypatch, tmp_path):
        """Re-merge of Claude settings does not duplicate SOT digest in SessionStart."""
        from merge_settings import merge_settings

        monkeypatch.delenv("AI_MEMORY_SOT_HOOKS", raising=False)
        monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
        monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)
        monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(tmp_path / "fake_install"))

        settings_path = tmp_path / "settings.json"
        hooks_dir = str(tmp_path / "hooks")

        # First install
        merge_settings(str(settings_path), hooks_dir, "test-project")
        # Second install (re-merge)
        merge_settings(str(settings_path), hooks_dir, "test-project")

        result = json.loads(settings_path.read_text())
        session_start = result["hooks"]["SessionStart"]
        digest_cmds = [
            h["command"]
            for w in session_start
            for h in w.get("hooks", [])
            if "sot_digest_session_start.py" in h.get("command", "")
        ]
        assert len(digest_cmds) == 1, (
            f"Expected exactly 1 sot_digest_session_start.py in SessionStart after re-merge, "
            f"got {len(digest_cmds)}"
        )

    def test_remerge_no_duplicate_stop(self, monkeypatch, tmp_path):
        """Re-merge of Claude settings does not duplicate SOT drift in Stop."""
        from merge_settings import merge_settings

        monkeypatch.delenv("AI_MEMORY_SOT_HOOKS", raising=False)
        monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
        monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)
        monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(tmp_path / "fake_install"))

        settings_path = tmp_path / "settings.json"
        hooks_dir = str(tmp_path / "hooks")

        merge_settings(str(settings_path), hooks_dir, "test-project")
        merge_settings(str(settings_path), hooks_dir, "test-project")

        result = json.loads(settings_path.read_text())
        stop = result["hooks"]["Stop"]
        drift_cmds = [
            h["command"]
            for w in stop
            for h in w.get("hooks", [])
            if "sot_drift_stop.py" in h.get("command", "")
        ]
        assert len(drift_cmds) == 1, (
            f"Expected exactly 1 sot_drift_stop.py in Stop after re-merge, "
            f"got {len(drift_cmds)}"
        )

    def test_strip_survival_when_scripts_exist(self, monkeypatch, tmp_path):
        """_remove_dead_hooks does NOT strip SOT hooks when script files exist on disk.

        Populates a mock install dir with real (empty) sot_digest_session_start.py and
        sot_drift_stop.py files, runs merge_settings twice, and asserts both hooks survive
        at count==1. Directly satisfies DONE-WHEN: 'strip-survival on populated install'.
        """
        from merge_settings import merge_settings

        # Build a mock install dir with the SOT scripts present
        scripts_dir = tmp_path / "install" / ".claude" / "hooks" / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "sot_digest_session_start.py").write_text("")
        (scripts_dir / "sot_drift_stop.py").write_text("")

        monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(tmp_path / "install"))
        monkeypatch.delenv("AI_MEMORY_SOT_HOOKS", raising=False)
        monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
        monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)

        settings_path = tmp_path / "settings.json"
        hooks_dir = str(scripts_dir)

        merge_settings(str(settings_path), hooks_dir, "test-project")
        merge_settings(str(settings_path), hooks_dir, "test-project")

        result = json.loads(settings_path.read_text())

        digest_cmds = [
            h["command"]
            for w in result["hooks"]["SessionStart"]
            for h in w.get("hooks", [])
            if "sot_digest_session_start.py" in h.get("command", "")
        ]
        assert (
            len(digest_cmds) == 1
        ), f"sot_digest_session_start.py was stripped or duplicated: count={len(digest_cmds)}"

        drift_cmds = [
            h["command"]
            for w in result["hooks"]["Stop"]
            for h in w.get("hooks", [])
            if "sot_drift_stop.py" in h.get("command", "")
        ]
        assert (
            len(drift_cmds) == 1
        ), f"sot_drift_stop.py was stripped or duplicated: count={len(drift_cmds)}"


# ---------------------------------------------------------------------------
# Gemini — write_gemini_config
# ---------------------------------------------------------------------------


class TestGeminiSotRegistration:
    def test_sot_hooks_registered_by_default(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """Gemini config contains SOT digest (SessionStart) + drift (PreCompress) by default."""
        project = tmp_path / "proj"
        project.mkdir()
        result = _call(
            install_sh_no_main,
            "write_gemini_config",
            project,
            install_dir,
            extra_env={"AI_MEMORY_SOT_HOOKS": "on"},
        )
        assert result.returncode == 0, result.stderr

        cfg = json.loads((project / ".gemini" / "settings.json").read_text())
        hooks = cfg["hooks"]

        session_cmds = [
            h["command"]
            for w in hooks.get("SessionStart", [])
            for h in w.get("hooks", [])
        ]
        assert any(
            "sot_digest_session_start.py" in cmd for cmd in session_cmds
        ), "gemini/sot_digest_session_start.py must appear in SessionStart"

        compress_cmds = [
            h["command"]
            for w in hooks.get("PreCompress", [])
            for h in w.get("hooks", [])
        ]
        assert any(
            "sot_drift.py" in cmd for cmd in compress_cmds
        ), "gemini/sot_drift.py must appear in PreCompress"

    def test_sot_hooks_absent_when_gate_off(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """Gemini config has no SOT hooks when AI_MEMORY_SOT_HOOKS=off."""
        project = tmp_path / "proj"
        project.mkdir()
        result = _call(
            install_sh_no_main,
            "write_gemini_config",
            project,
            install_dir,
            extra_env={"AI_MEMORY_SOT_HOOKS": "off"},
        )
        assert result.returncode == 0, result.stderr

        cfg = json.loads((project / ".gemini" / "settings.json").read_text())
        hooks = cfg["hooks"]

        all_cmds = [
            h["command"]
            for event_hooks in hooks.values()
            for w in event_hooks
            for h in w.get("hooks", [])
        ]
        assert not any(
            "sot_digest_session_start.py" in cmd for cmd in all_cmds
        ), "sot_digest_session_start.py must NOT be registered when gate is off"
        assert not any(
            "sot_drift" in cmd for cmd in all_cmds
        ), "sot_drift must NOT be registered when gate is off"

    def test_sot_session_start_matcher_is_star(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """Gemini SOT digest SessionStart uses '.*' matcher (matches existing sibling)."""
        project = tmp_path / "proj"
        project.mkdir()
        result = _call(
            install_sh_no_main,
            "write_gemini_config",
            project,
            install_dir,
            extra_env={"AI_MEMORY_SOT_HOOKS": "on"},
        )
        assert result.returncode == 0, result.stderr

        cfg = json.loads((project / ".gemini" / "settings.json").read_text())
        sot_wrappers = [
            w
            for w in cfg["hooks"].get("SessionStart", [])
            if any(
                "sot_digest_session_start.py" in h.get("command", "")
                for h in w.get("hooks", [])
            )
        ]
        assert sot_wrappers, "SOT digest wrapper not found in Gemini SessionStart"
        assert (
            sot_wrappers[0].get("matcher") == ".*"
        ), "Gemini SOT digest matcher must be '.*' to match existing sibling"


# ---------------------------------------------------------------------------
# Cursor — write_cursor_config
# ---------------------------------------------------------------------------


class TestCursorSotRegistration:
    def test_sot_hooks_registered_by_default(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """Cursor config contains SOT digest (sessionStart) + drift (preCompact) by default."""
        project = tmp_path / "proj"
        project.mkdir()
        result = _call(
            install_sh_no_main,
            "write_cursor_config",
            project,
            install_dir,
            extra_env={"AI_MEMORY_SOT_HOOKS": "on"},
        )
        assert result.returncode == 0, result.stderr

        cfg = json.loads((project / ".cursor" / "hooks.json").read_text())
        hooks = cfg["hooks"]

        session_cmds = [e["command"] for e in hooks.get("sessionStart", [])]
        assert any(
            "sot_digest_session_start.py" in cmd for cmd in session_cmds
        ), "cursor/sot_digest_session_start.py must appear in sessionStart"

        compact_cmds = [e["command"] for e in hooks.get("preCompact", [])]
        assert any(
            "sot_drift.py" in cmd for cmd in compact_cmds
        ), "cursor/sot_drift.py must appear in preCompact"

    def test_sot_hooks_absent_when_gate_off(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """Cursor config has no SOT hooks when AI_MEMORY_SOT_HOOKS=off."""
        project = tmp_path / "proj"
        project.mkdir()
        result = _call(
            install_sh_no_main,
            "write_cursor_config",
            project,
            install_dir,
            extra_env={"AI_MEMORY_SOT_HOOKS": "off"},
        )
        assert result.returncode == 0, result.stderr

        cfg = json.loads((project / ".cursor" / "hooks.json").read_text())
        hooks = cfg["hooks"]

        all_cmds = [
            e["command"]
            for event_cmds in hooks.values()
            if isinstance(event_cmds, list)
            for e in event_cmds
            if isinstance(e, dict) and "command" in e
        ]
        assert not any(
            "sot_digest_session_start.py" in cmd for cmd in all_cmds
        ), "sot_digest_session_start.py must NOT be registered in Cursor when gate is off"
        assert not any(
            "sot_drift" in cmd for cmd in all_cmds
        ), "sot_drift must NOT be registered in Cursor when gate is off"

    def test_sot_session_start_no_matcher(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """Cursor SOT digest sessionStart entry has no matcher field (matches sibling shape)."""
        project = tmp_path / "proj"
        project.mkdir()
        _call(
            install_sh_no_main,
            "write_cursor_config",
            project,
            install_dir,
            extra_env={"AI_MEMORY_SOT_HOOKS": "on"},
        )
        cfg = json.loads((project / ".cursor" / "hooks.json").read_text())
        sot_entries = [
            e
            for e in cfg["hooks"].get("sessionStart", [])
            if "sot_digest_session_start.py" in e.get("command", "")
        ]
        assert sot_entries, "SOT digest entry not found in Cursor sessionStart"
        assert (
            "matcher" not in sot_entries[0]
        ), "Cursor sessionStart SOT entry must have no matcher field (per sibling shape)"


# ---------------------------------------------------------------------------
# Codex — write_codex_config
# ---------------------------------------------------------------------------


class TestCodexSotRegistration:
    def test_sot_hooks_registered_by_default(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """Codex config contains SOT digest (SessionStart) + drift (Stop) by default."""
        project = tmp_path / "proj"
        project.mkdir()
        result = _call(
            install_sh_no_main,
            "write_codex_config",
            project,
            install_dir,
            extra_env={"AI_MEMORY_SOT_HOOKS": "on"},
        )
        assert result.returncode == 0, result.stderr

        cfg = json.loads((project / ".codex" / "hooks.json").read_text())
        hooks = cfg["hooks"]

        session_cmds = [
            h["command"]
            for w in hooks.get("SessionStart", [])
            for h in w.get("hooks", [])
        ]
        assert any(
            "sot_digest_session_start.py" in cmd for cmd in session_cmds
        ), "codex/sot_digest_session_start.py must appear in SessionStart"

        stop_cmds = [
            h["command"] for w in hooks.get("Stop", []) for h in w.get("hooks", [])
        ]
        assert any(
            "sot_drift.py" in cmd for cmd in stop_cmds
        ), "codex/sot_drift.py must appear in Stop"

    def test_sot_hooks_absent_when_gate_off(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """Codex config has no SOT hooks when AI_MEMORY_SOT_HOOKS=off."""
        project = tmp_path / "proj"
        project.mkdir()
        result = _call(
            install_sh_no_main,
            "write_codex_config",
            project,
            install_dir,
            extra_env={"AI_MEMORY_SOT_HOOKS": "off"},
        )
        assert result.returncode == 0, result.stderr

        cfg = json.loads((project / ".codex" / "hooks.json").read_text())
        hooks = cfg["hooks"]

        all_cmds = [
            h["command"]
            for event_hooks in hooks.values()
            for w in event_hooks
            for h in w.get("hooks", [])
            if isinstance(h, dict) and "command" in h
        ]
        assert not any(
            "sot_digest_session_start.py" in cmd for cmd in all_cmds
        ), "sot_digest_session_start.py must NOT be registered in Codex when gate is off"
        assert not any(
            "sot_drift" in cmd for cmd in all_cmds
        ), "sot_drift must NOT be registered in Codex when gate is off"

    def test_sot_session_start_matcher_is_star(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """Codex SOT digest SessionStart uses '.*' matcher (matches existing sibling)."""
        project = tmp_path / "proj"
        project.mkdir()
        _call(
            install_sh_no_main,
            "write_codex_config",
            project,
            install_dir,
            extra_env={"AI_MEMORY_SOT_HOOKS": "on"},
        )
        cfg = json.loads((project / ".codex" / "hooks.json").read_text())
        sot_wrappers = [
            w
            for w in cfg["hooks"].get("SessionStart", [])
            if any(
                "sot_digest_session_start.py" in h.get("command", "")
                for h in w.get("hooks", [])
            )
        ]
        assert sot_wrappers, "SOT digest wrapper not found in Codex SessionStart"
        assert (
            sot_wrappers[0].get("matcher") == ".*"
        ), "Codex SOT digest matcher must be '.*' to match existing sibling"

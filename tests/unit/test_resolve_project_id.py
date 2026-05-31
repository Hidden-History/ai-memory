"""Contract tests for the shared resolve_project_id() helper (BUG-314 / BP-166 F3).

resolve_project_id is the single project-scope resolver every read + write + wrapper
site routes through. Precedence: explicit -> AI_MEMORY_PROJECT_ID env -> detect_project(cwd)
-> fail-loud ValueError. These tests pin that contract plus the env!=cwd warn-not-fail
policy (OQ-1). They complement tests/test_project.py (which covers detect_project itself).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from memory.project import resolve_project_id  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)


def _make_git_repo(path: Path, remote_url: str) -> None:
    """Create a minimal repo dir whose .git/config carries a remote origin url."""
    git_dir = path / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "config").write_text(
        f'[remote "origin"]\n\turl = {remote_url}\n', encoding="utf-8"
    )


class TestPrecedence:
    def test_explicit_beats_env_and_cwd(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", "env-project")
        _make_git_repo(tmp_path, "https://github.com/acme/cwd-repo.git")
        assert (
            resolve_project_id(str(tmp_path), explicit="Explicit/Repo")
            == "explicit/repo"
        )

    def test_env_beats_cwd(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", "env-project")
        _make_git_repo(tmp_path, "https://github.com/acme/cwd-repo.git")
        assert resolve_project_id(str(tmp_path)) == "env-project"

    def test_env_is_normalized(self, monkeypatch, tmp_path):
        # Matches detect_project normalization so read==write stay consistent.
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", "My Project")
        assert resolve_project_id(str(tmp_path)) == "my-project"

    def test_env_owner_repo_slug_preserved(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", "Hidden-History/ai-memory")
        assert resolve_project_id(str(tmp_path)) == "hidden-history/ai-memory"

    def test_cwd_git_fallback_when_no_env(self, tmp_path):
        _make_git_repo(tmp_path, "git@github.com:Acme/Cwd-Repo.git")
        assert resolve_project_id(str(tmp_path)) == "acme/cwd-repo"

    def test_explicit_blank_falls_through_to_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", "env-project")
        assert resolve_project_id(str(tmp_path), explicit="   ") == "env-project"


def _write_marker(path: Path, body: str) -> None:
    (path / ".ai-memory-project").write_text(body, encoding="utf-8")


class TestMarkerFile:
    """The committed .ai-memory-project marker sits between env and git-remote."""

    def test_marker_resolves_when_no_env(self, tmp_path):
        _write_marker(tmp_path, "Acme/Widget\n")
        assert resolve_project_id(str(tmp_path)) == "acme/widget"

    def test_marker_beats_cwd_git_remote(self, tmp_path):
        # Marker is a more specific per-workspace declaration than the git slug.
        _make_git_repo(tmp_path, "https://github.com/other/git-repo.git")
        _write_marker(tmp_path, "declared/marker\n")
        assert resolve_project_id(str(tmp_path)) == "declared/marker"

    def test_env_overrides_marker(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", "env-wins")
        _write_marker(tmp_path, "marker-loses\n")
        assert resolve_project_id(str(tmp_path)) == "env-wins"

    def test_explicit_overrides_marker(self, tmp_path):
        _write_marker(tmp_path, "marker-loses\n")
        assert (
            resolve_project_id(str(tmp_path), explicit="Explicit/Win") == "explicit/win"
        )

    def test_marker_found_by_walking_up(self, tmp_path):
        _write_marker(tmp_path, "root-marker\n")
        sub = tmp_path / "a" / "b" / "c"
        sub.mkdir(parents=True)
        assert resolve_project_id(str(sub)) == "root-marker"

    def test_comment_and_blank_lines_ignored(self, tmp_path):
        _write_marker(tmp_path, "# this workspace's project id\n\nteam/service\n")
        assert resolve_project_id(str(tmp_path)) == "team/service"

    def test_comment_only_marker_falls_through(self, tmp_path):
        # A marker with no id line is not a declaration → fall through to fail-loud.
        plain = tmp_path / "plain"
        plain.mkdir()
        _write_marker(plain, "# nothing declared here\n")
        with pytest.raises(ValueError, match="project detection failed"):
            resolve_project_id(str(plain))


class TestFailLoud:
    def test_no_env_no_git_raises(self, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        with pytest.raises(ValueError, match="project detection failed"):
            resolve_project_id(str(plain))


class TestMismatchPolicy:
    def test_env_neq_cwd_warns_and_prefers_env(self, monkeypatch, tmp_path, caplog):
        """OQ-1: disagreement warns loudly but resolves to the env (never hard-fails)."""
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", "workspace-a")
        _make_git_repo(tmp_path, "https://github.com/acme/other-b.git")
        with caplog.at_level(logging.WARNING, logger="memory.project"):
            resolved = resolve_project_id(str(tmp_path))
        assert resolved == "workspace-a"
        assert any(
            r.msg == "project_env_cwd_mismatch" for r in caplog.records
        ), "expected a loud env!=cwd mismatch warning"

    def test_env_agrees_with_cwd_no_warning(self, monkeypatch, tmp_path, caplog):
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", "acme/same-repo")
        _make_git_repo(tmp_path, "https://github.com/Acme/Same-Repo.git")
        with caplog.at_level(logging.WARNING, logger="memory.project"):
            resolve_project_id(str(tmp_path))
        assert not any(r.msg == "project_env_cwd_mismatch" for r in caplog.records)

    def test_env_set_no_git_cwd_no_warning(self, monkeypatch, tmp_path, caplog):
        # The common case: env set, cwd has no git remote -> not a disagreement.
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", "workspace-a")
        plain = tmp_path / "plain"
        plain.mkdir()
        with caplog.at_level(logging.WARNING, logger="memory.project"):
            assert resolve_project_id(str(plain)) == "workspace-a"
        assert not any(r.msg == "project_env_cwd_mismatch" for r in caplog.records)


class TestWrapperNonClobber:
    """run-with-env.sh must NOT clobber a caller-set AI_MEMORY_PROJECT_ID, and (scoped
    Part D) must NOT inject the install-global id into operator scripts at all.

    Coverage spans both the propagated env var and the *effective* group_id the
    storage floor receives (the resolver's answer through the real wrapper), per
    BP-166 Q4 Case 4."""

    def _stage_install(self, tmp_path: Path, install_project: str) -> Path:
        install = tmp_path / "install"
        (install / "docker").mkdir(parents=True)
        (install / "docker" / ".env").write_text(
            f"AI_MEMORY_PROJECT_ID={install_project}\nQDRANT_API_KEY=test-key\n",
            encoding="utf-8",
        )
        venv_bin = install / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        (venv_bin / "python").symlink_to(sys.executable)
        return install

    def _run_wrapper(
        self,
        install: Path,
        caller_env: dict[str, str],
        *,
        probe_body: str | None = None,
        cwd: str | None = None,
    ) -> str:
        wrapper = (
            Path(__file__).resolve().parents[2]
            / "scripts"
            / "memory"
            / "run-with-env.sh"
        )
        probe = install / "probe.py"
        if probe_body is None:
            probe_body = (
                'import os\nprint(os.environ.get("AI_MEMORY_PROJECT_ID", ""))\n'
            )
        probe.write_text(probe_body, encoding="utf-8")
        env = {**os.environ, "AI_MEMORY_INSTALL_DIR": str(install)}
        # Explicitly clear the scope var before layering caller_env so each case is
        # robust regardless of the runner's ambient environment or the autouse
        # _clear_env fixture: caller_env is the ONLY source of a set id here.
        env.pop("AI_MEMORY_PROJECT_ID", None)
        env.update(caller_env)
        env.pop("AI_MEMORY_ENV_FILE", None)
        env.pop("AI_MEMORY_SECRETS_FILE", None)
        result = subprocess.run(
            ["bash", str(wrapper), str(probe)],
            env=env,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def test_caller_id_beats_install_default(self, tmp_path):
        install = self._stage_install(tmp_path, install_project="install-b")
        out = self._run_wrapper(install, {"AI_MEMORY_PROJECT_ID": "caller-a"})
        assert out == "caller-a", "wrapper clobbered a caller-set project id"

    def test_caller_id_is_effective_resolved_group_id(self, tmp_path):
        # BP-166 Q4 Case 4 asks for "effective group_id == A": assert not just the
        # raw env var but the id the storage floor would actually receive — i.e.
        # what resolve_project_id() returns through the real wrapper. The probe
        # runs from a non-git cwd so env A is the unambiguous resolved scope while
        # the install .env says B.
        install = self._stage_install(tmp_path, install_project="install-b")
        nongit = tmp_path / "caller_ws"
        nongit.mkdir()
        # Load project.py STANDALONE (it imports only stdlib) so the probe runs the
        # real resolve_project_id without needing the install's third-party deps —
        # the staged .venv/bin/python is a bare symlink with no site-packages.
        project_py = _SRC / "memory" / "project.py"
        probe_body = (
            "import os, importlib.util\n"
            f"_spec = importlib.util.spec_from_file_location('_proj', {str(project_py)!r})\n"
            "_m = importlib.util.module_from_spec(_spec)\n"
            "_spec.loader.exec_module(_m)\n"
            "print(_m.resolve_project_id(os.getcwd()))\n"
        )
        out = self._run_wrapper(
            install,
            {"AI_MEMORY_PROJECT_ID": "caller-a"},
            probe_body=probe_body,
            cwd=str(nongit),
        )
        assert out == "caller-a", (
            "effective resolved group_id was not the caller-set id A "
            "(wrapper clobbered it or the install-global B leaked into resolution)"
        )

    def test_install_global_not_injected(self, tmp_path):
        # Scoped Part D: with no caller env (explicitly unset in _run_wrapper), the
        # wrapper must NOT inject the install-global project id into the operator
        # script.
        install = self._stage_install(tmp_path, install_project="install-b")
        out = self._run_wrapper(install, {})
        assert out == "", (
            "wrapper injected the install-global AI_MEMORY_PROJECT_ID into an "
            "operator script (confused-deputy regression)"
        )

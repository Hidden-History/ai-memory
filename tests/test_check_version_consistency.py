"""Tests for scripts/check_version_consistency.py (BUG-307).

Covers the three-marker consistency check:
- the agree case (all markers match -> exit 0)
- the disagree case (a marker drifts -> exit 1, disagreement reported)
- tag/release mode (markers must also equal the tag and CHANGELOG heading)
- the live repository markers actually agree
"""

import importlib.util
from pathlib import Path

import pytest

# Load scripts/check_version_consistency.py. The script lives outside any
# importable package, so load it by file location (mirrors test_version.py).
_SCRIPT = Path(__file__).parent.parent / "scripts" / "check_version_consistency.py"
_spec = importlib.util.spec_from_file_location("check_version_consistency", _SCRIPT)
cvc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cvc)

REPO_ROOT = Path(__file__).parent.parent


def _write_repo(
    root: Path,
    version_txt: str,
    pyproject: str,
    version_py: str,
    changelog: str | None = None,
) -> None:
    """Create a minimal repo tree with the version markers under ``root``."""
    (root / "version.txt").write_text(version_txt, encoding="utf-8")
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "ai-memory"\nversion = "{pyproject}"\n'
        '\n[tool.ruff]\ntarget-version = "py310"\n',
        encoding="utf-8",
    )
    version_dir = root / "src" / "memory"
    version_dir.mkdir(parents=True, exist_ok=True)
    (version_dir / "__version__.py").write_text(
        f'__version__ = "{version_py}"\n'
        '__version_info__ = tuple(int(p) for p in __version__.split("."))\n',
        encoding="utf-8",
    )
    if changelog is not None:
        (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")


_CHANGELOG = (
    "# Changelog\n\n"
    "## [Unreleased]\n\n"
    "## [2.4.1] - 2026-05-16\n\n### Fixed\n\n- something\n"
)


class TestMarkerReaders:
    """The individual marker readers parse the expected values."""

    def test_readers_return_marker_values(self, tmp_path):
        _write_repo(tmp_path, "2.4.1", "2.4.1", "2.4.1", _CHANGELOG)

        assert cvc.read_version_txt(tmp_path) == "2.4.1"
        assert cvc.read_pyproject_version(tmp_path) == "2.4.1"
        assert cvc.read_version_py(tmp_path) == "2.4.1"
        assert cvc.read_changelog_release_version(tmp_path) == "2.4.1"

    def test_pyproject_reader_ignores_other_version_keys(self, tmp_path):
        """``target-version`` under [tool.ruff] must not be mistaken for it."""
        _write_repo(tmp_path, "2.4.1", "2.4.1", "2.4.1")
        assert cvc.read_pyproject_version(tmp_path) == "2.4.1"

    def test_missing_marker_raises_marker_error(self, tmp_path):
        with pytest.raises(cvc.MarkerError):
            cvc.read_version_txt(tmp_path)

    def test_pyproject_reader_missing_file_raises(self, tmp_path):
        with pytest.raises(cvc.MarkerError):
            cvc.read_pyproject_version(tmp_path)

    def test_pyproject_reader_missing_project_table_raises(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[tool.ruff]\ntarget-version = "py310"\n', encoding="utf-8"
        )
        with pytest.raises(cvc.MarkerError):
            cvc.read_pyproject_version(tmp_path)

    def test_pyproject_reader_missing_version_key_raises(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "ai-memory"\n', encoding="utf-8"
        )
        with pytest.raises(cvc.MarkerError):
            cvc.read_pyproject_version(tmp_path)

    def test_version_py_reader_missing_file_raises(self, tmp_path):
        with pytest.raises(cvc.MarkerError):
            cvc.read_version_py(tmp_path)

    def test_version_py_reader_missing_assignment_raises(self, tmp_path):
        version_dir = tmp_path / "src" / "memory"
        version_dir.mkdir(parents=True)
        (version_dir / "__version__.py").write_text(
            '"""No version assignment here."""\n', encoding="utf-8"
        )
        with pytest.raises(cvc.MarkerError):
            cvc.read_version_py(tmp_path)


class TestCheckConsistency:
    """The pure comparison logic."""

    def test_agree_case_returns_no_errors(self):
        markers = {"a": "2.4.1", "b": "2.4.1", "c": "2.4.1"}
        assert cvc.check_consistency(markers) == []

    def test_disagree_case_reports_markers_and_values(self):
        markers = {"a": "2.4.1", "b": "2.3.2", "c": "2.4.1"}
        errors = cvc.check_consistency(markers)
        assert len(errors) == 1
        # Every marker name and value appears in the message.
        assert "2.4.1" in errors[0] and "2.3.2" in errors[0]
        assert "a=" in errors[0] and "b=" in errors[0] and "c=" in errors[0]

    def test_tag_mode_agree(self):
        markers = {"a": "2.4.2", "b": "2.4.2", "c": "2.4.2"}
        errors = cvc.check_consistency(markers, tag="v2.4.2", changelog_version="2.4.2")
        assert errors == []

    def test_tag_mode_rejects_tag_mismatch(self):
        markers = {"a": "2.4.1", "b": "2.4.1", "c": "2.4.1"}
        errors = cvc.check_consistency(markers, tag="v2.4.2", changelog_version="2.4.1")
        # One per marker that disagrees with the tag.
        assert any("release tag" in e for e in errors)
        assert len(errors) >= 3

    def test_tag_mode_rejects_changelog_mismatch(self):
        markers = {"a": "2.4.2", "b": "2.4.2", "c": "2.4.2"}
        errors = cvc.check_consistency(markers, tag="v2.4.2", changelog_version="2.4.1")
        assert any("CHANGELOG" in e for e in errors)


class TestMainExitCodes:
    """End-to-end exit codes via ``main()``."""

    def test_main_agree_exits_zero(self, tmp_path):
        _write_repo(tmp_path, "2.4.1", "2.4.1", "2.4.1", _CHANGELOG)
        assert cvc.main(["--root", str(tmp_path)]) == 0

    def test_main_disagree_exits_one(self, tmp_path, capsys):
        _write_repo(tmp_path, "2.4.1", "2.4.1", "2.3.2", _CHANGELOG)
        assert cvc.main(["--root", str(tmp_path)]) == 1
        captured = capsys.readouterr()
        assert "FAILED" in captured.err
        assert "2.3.2" in captured.err

    def test_main_tag_mode_agree_exits_zero(self, tmp_path):
        _write_repo(tmp_path, "2.4.1", "2.4.1", "2.4.1", _CHANGELOG)
        assert cvc.main(["--root", str(tmp_path), "--tag", "v2.4.1"]) == 0

    def test_main_tag_mode_mismatch_exits_one(self, tmp_path):
        _write_repo(tmp_path, "2.4.1", "2.4.1", "2.4.1", _CHANGELOG)
        assert cvc.main(["--root", str(tmp_path), "--tag", "v2.4.2"]) == 1

    def test_main_tag_mode_changelog_mismatch_exits_one(self, tmp_path, capsys):
        # All three markers agree with the tag, but the CHANGELOG's latest
        # release heading lags behind it.
        _write_repo(tmp_path, "2.4.2", "2.4.2", "2.4.2", _CHANGELOG)
        assert cvc.main(["--root", str(tmp_path), "--tag", "v2.4.2"]) == 1
        captured = capsys.readouterr()
        assert "FAILED" in captured.err
        assert "CHANGELOG" in captured.err

    def test_main_unreadable_marker_exits_two(self, tmp_path, capsys):
        # No marker files written at all.
        assert cvc.main(["--root", str(tmp_path)]) == 2
        assert "cannot read" in capsys.readouterr().err


class TestEmitActionsError:
    """The GitHub Actions annotation path."""

    def test_emits_single_line_annotation_under_github_actions(
        self, monkeypatch, capsys
    ):
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        cvc._emit_actions_error("line one\nline two")
        out = capsys.readouterr().out.strip()
        # A workflow command must be a single line.
        assert "\n" not in out
        assert out.startswith("::error ")
        assert "title=Version consistency::" in out
        # The newline is replaced by a space, not dropped.
        assert "line one line two" in out

    def test_emits_nothing_outside_github_actions(self, monkeypatch, capsys):
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        cvc._emit_actions_error("some error")
        assert capsys.readouterr().out == ""


class TestLiveRepository:
    """The real repository markers must agree (regression guard for BUG-307)."""

    def test_live_markers_are_consistent(self):
        markers = cvc.collect_markers(REPO_ROOT)
        assert (
            cvc.check_consistency(markers) == []
        ), f"repository version markers disagree: {markers}"

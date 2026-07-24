"""Tests for the aim-verify framework (PLAN-037 P1).

Loaded via importlib (no package __init__) so the suite runs standalone
against the script file, matching the sibling aim-sot test convention.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "aim_verify.py"
_spec = importlib.util.spec_from_file_location("aim_verify", _SCRIPT)
av = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = av  # dataclasses needs the module registered before exec
_spec.loader.exec_module(av)


def _result(
    check_id="c", category="test", status="pass", message="ok", remediation=None
):
    return av.CheckResult(
        check_id=check_id,
        category=category,
        status=status,
        message=message,
        remediation=remediation,
    )


class _FakeCheck:
    """A minimal Check for exercising the runner without touching the real registry."""

    def __init__(self, check_id, status, *, raises=False):
        self.id = check_id
        self.category = "fake"
        self._status = status
        self._raises = raises

    def run(self, ctx):
        if self._raises:
            raise RuntimeError("boom")
        return av.CheckResult(
            check_id=self.id, category=self.category, status=self._status, message="m"
        )


# ---------------------------------------------------------------------------
# Runner aggregation — accumulates ALL results, no fail-fast.
# ---------------------------------------------------------------------------


def test_runner_accumulates_all_results_no_fail_fast():
    registry = [
        _FakeCheck("a", "fail"),
        _FakeCheck("b", "pass"),
        _FakeCheck("c", "warn"),
    ]
    results = av.run_checks(registry=registry)
    assert [r.check_id for r in results] == ["a", "b", "c"]
    assert [r.status for r in results] == ["fail", "pass", "warn"]


def test_runner_isolates_a_crashing_check_as_its_own_fail():
    registry = [_FakeCheck("ok", "pass"), _FakeCheck("boom", "pass", raises=True)]
    results = av.run_checks(registry=registry)
    assert len(results) == 2
    assert results[0].status == "pass"
    assert results[1].status == "fail"
    assert "boom" in results[1].message or "crashed" in results[1].message


class _BadReturnCheck:
    """A Check whose run() forgets its return statement — a plausible real
    bug that must not crash the runner or reach render_json/worst_status."""

    id = "bad-return"
    category = "fake"

    def run(self, ctx):
        return None


def test_runner_isolates_a_non_checkresult_return_as_its_own_fail():
    registry = [_FakeCheck("ok", "pass"), _BadReturnCheck()]
    results = av.run_checks(registry=registry)
    assert len(results) == 2
    assert results[0].status == "pass"
    assert results[1].check_id == "bad-return"
    assert results[1].category == "fake"
    assert results[1].status == "fail"
    # Must not have crashed reaching this point — worst_status/exit_code_for
    # operate on real CheckResult objects, not the offending None.
    assert av.worst_status(results) == "fail"
    assert av.exit_code_for(results) == 1


def test_checkresult_rejects_unknown_status():
    with pytest.raises(ValueError):
        av.CheckResult(check_id="x", category="y", status="bogus", message="m")


# ---------------------------------------------------------------------------
# Worst-severity -> exit-code model.
# ---------------------------------------------------------------------------


def test_worst_status_all_pass():
    results = [_result(status="pass"), _result(status="pass")]
    assert av.worst_status(results) == "pass"
    assert av.exit_code_for(results) == 0


def test_worst_status_warn_only_does_not_fail_the_run():
    results = [_result(status="pass"), _result(status="warn")]
    assert av.worst_status(results) == "warn"
    assert av.exit_code_for(results) == 0


def test_worst_status_any_fail_is_nonzero_exit():
    results = [_result(status="pass"), _result(status="warn"), _result(status="fail")]
    assert av.worst_status(results) == "fail"
    assert av.exit_code_for(results) == 1


def test_worst_status_empty_results_is_pass():
    assert av.worst_status([]) == "pass"
    assert av.exit_code_for([]) == 0


def test_skip_ranks_with_pass_never_fails_the_run():
    results = [_result(status="skip"), _result(status="skip")]
    assert av.worst_status(results) == "skip"
    assert av.exit_code_for(results) == 0


# ---------------------------------------------------------------------------
# Renderers — json shape + human glyphs, both routed through redact().
# ---------------------------------------------------------------------------


def test_render_json_shape_is_typed_and_stable():
    results = [
        _result(
            check_id="c1",
            category="cat",
            status="fail",
            message="msg1",
            remediation="fix1",
        ),
        _result(check_id="c2", category="cat", status="pass", message="msg2"),
    ]
    payload = av.render_json(results)
    assert payload == [
        {
            "check": "c1",
            "status": "fail",
            "severity": 2,
            "message": "msg1",
            "remediation": "fix1",
        },
        {
            "check": "c2",
            "status": "pass",
            "severity": 0,
            "message": "msg2",
            "remediation": None,
        },
    ]


def test_render_human_shows_glyph_and_remediation_on_fail_only():
    results = [
        _result(check_id="ok", status="pass", message="all good"),
        _result(check_id="broken", status="fail", message="bad", remediation="do X"),
    ]
    out = av.render_human(results)
    assert "✓ [test] ok: all good" in out
    assert "✗ [test] broken: bad" in out
    assert "do X" in out


def test_redact_is_a_documented_passthrough_stub_in_p1():
    results = [_result(message="secret-looking-value-should-not-be-touched-yet")]
    assert av.redact(results) == results


# ---------------------------------------------------------------------------
# The one example check — install-dir-present — pass and fail paths.
# ---------------------------------------------------------------------------


def test_install_dir_check_passes_when_dir_and_subdirs_exist(tmp_path, monkeypatch):
    install_dir = tmp_path / "ai-memory"
    for sub in ("src", "scripts", "docker"):
        (install_dir / sub).mkdir(parents=True)
    monkeypatch.setenv(av.INSTALL_DIR_ENV, str(install_dir))

    result = av.InstallDirCheck().run(ctx={})
    assert result.status == "pass"
    assert result.check_id == "install-dir-present"


def test_install_dir_check_fails_when_dir_missing(tmp_path, monkeypatch):
    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv(av.INSTALL_DIR_ENV, str(missing))

    result = av.InstallDirCheck().run(ctx={})
    assert result.status == "fail"
    assert result.remediation


def test_install_dir_check_fails_when_subdir_missing(tmp_path, monkeypatch):
    install_dir = tmp_path / "ai-memory"
    (install_dir / "src").mkdir(parents=True)
    # "scripts" and "docker" intentionally absent
    monkeypatch.setenv(av.INSTALL_DIR_ENV, str(install_dir))

    result = av.InstallDirCheck().run(ctx={})
    assert result.status == "fail"
    assert "scripts" in result.message
    assert "docker" in result.message


@pytest.mark.parametrize("blank_value", ["", "   "])
def test_install_dir_check_blank_env_var_falls_back_to_default(
    blank_value, monkeypatch, tmp_path
):
    # A present-but-empty OR whitespace-only env var must be treated like an
    # absent one, not resolved via Path("   ").expanduser() -> a bogus
    # relative path under cwd, which would spuriously pass or fail on
    # incidental cwd contents rather than the real default.
    fake_default = tmp_path / "default-install"
    for sub in ("src", "scripts", "docker"):
        (fake_default / sub).mkdir(parents=True)
    monkeypatch.setattr(av, "DEFAULT_INSTALL_DIR", str(fake_default))
    monkeypatch.setenv(av.INSTALL_DIR_ENV, blank_value)

    result = av.InstallDirCheck().run(ctx={})
    assert result.status == "pass"
    assert result.evidence["install_dir"] == str(fake_default)


def test_install_dir_check_reports_truthfully_when_path_is_a_file(
    tmp_path, monkeypatch
):
    not_a_dir = tmp_path / "install-dir-but-actually-a-file"
    not_a_dir.write_text("oops")
    monkeypatch.setenv(av.INSTALL_DIR_ENV, str(not_a_dir))

    result = av.InstallDirCheck().run(ctx={})
    assert result.status == "fail"
    assert "not a directory" in result.message
    assert result.evidence["exists"] is True
    assert result.evidence["is_dir"] is False


def test_install_dir_check_reports_truthfully_when_path_is_a_symlink_to_a_file(
    tmp_path, monkeypatch
):
    real_file = tmp_path / "actual-file"
    real_file.write_text("oops")
    symlink = tmp_path / "install-dir-symlink"
    symlink.symlink_to(real_file)
    monkeypatch.setenv(av.INSTALL_DIR_ENV, str(symlink))

    result = av.InstallDirCheck().run(ctx={})
    assert result.status == "fail"
    assert "not a directory" in result.message
    assert result.evidence["exists"] is True
    assert result.evidence["is_dir"] is False


def test_example_check_is_registered_end_to_end(monkeypatch, tmp_path):
    """run -> render -> exit, exercised through the real module-level REGISTRY."""
    install_dir = tmp_path / "ai-memory"
    for sub in ("src", "scripts", "docker"):
        (install_dir / sub).mkdir(parents=True)
    monkeypatch.setenv(av.INSTALL_DIR_ENV, str(install_dir))

    results = av.run_checks()
    assert any(r.check_id == "install-dir-present" for r in results)
    assert av.exit_code_for(results) == 0

    payload = av.render_json(results)
    assert any(
        row["check"] == "install-dir-present" and row["status"] == "pass"
        for row in payload
    )


# ---------------------------------------------------------------------------
# CLI — stdin guard and --help.
# ---------------------------------------------------------------------------


def test_main_does_not_crash_when_stdin_is_none(monkeypatch, tmp_path, capsys):
    # Detached/pythonw environments can have sys.stdin is None; isatty()
    # would raise AttributeError on None.
    install_dir = tmp_path / "ai-memory"
    for sub in ("src", "scripts", "docker"):
        (install_dir / sub).mkdir(parents=True)
    monkeypatch.setenv(av.INSTALL_DIR_ENV, str(install_dir))
    monkeypatch.setattr(av.sys, "stdin", None)

    exit_code = av.main([])
    assert exit_code == 0


def test_help_does_not_dump_the_full_module_docstring(capsys):
    with pytest.raises(SystemExit):
        av.main(["--help"])
    out = capsys.readouterr().out
    # The module docstring's internal architecture/contract prose must not
    # leak into --help; only a short one-line description belongs there.
    assert "Standing contract" not in out
    assert "REPORT-ONLY" not in out

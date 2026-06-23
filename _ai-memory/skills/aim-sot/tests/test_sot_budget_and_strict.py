"""F-SOT-3 + OBS-SOT-1: drift-scan budgets and ``verify --strict``.

F-SOT-3: the two unbounded full-project walks (BP-039 ``tree_digest`` and the
candidate discovery scan) must stop on a wall-time / file-count budget and
signal a *truncation* rather than run past the [CL] hook cap and silently
produce zero findings. The signal must propagate through the engine JSON
(``budget_truncated``) so the Stop hook can warn instead of dying quietly.

OBS-SOT-1: ``aim_sot_verify.py --strict`` exits non-zero only on a FAIL verdict
(PASS / CONDITIONAL still exit 0; default behavior — always exit 0 — unchanged).

Run targeted only:
    pytest tests/test_sot_budget_and_strict.py
"""

import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


shadow = _load("aim_sot_shadow")
dp = _load("aim_sot_detect_propose")
verify = _load("aim_sot_verify")


def _populate(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


class _Clock:
    """Deterministic monotonic stand-in: returns each queued value once, then
    repeats the last one (so a budget deadline can be forced past at will)."""

    def __init__(self, values):
        self._values = list(values)

    def monotonic(self):
        if len(self._values) > 1:
            return self._values.pop(0)
        return self._values[0]


# --------------------------------------------------------------------------- #
# R1 — tree_digest budget (wall-time + file-count) with truncation signal
# --------------------------------------------------------------------------- #


def test_tree_digest_file_count_cap_truncates(tmp_path):
    _populate(tmp_path, {f"f{i}.txt": str(i) for i in range(10)})
    td = shadow.tree_digest(tmp_path, max_files=3)
    assert td.truncated is True
    assert td.file_count <= 3


def test_tree_digest_wall_time_budget_truncates(tmp_path, monkeypatch):
    """A blown wall-time budget stops the walk and flags truncation, even when
    the file count is tiny (the slow-filesystem case)."""
    _populate(tmp_path, {"a.txt": "1", "b.txt": "2", "c.txt": "3"})
    # start=100 → deadline=110; every subsequent check reads 9999 > 110.
    monkeypatch.setattr(shadow, "time", _Clock([100.0, 9999.0]))
    td = shadow.tree_digest(tmp_path, max_seconds=10.0)
    assert td.truncated is True
    assert td.file_count == 0  # truncated before hashing the first file


def test_tree_digest_default_budget_does_not_truncate_small_tree(tmp_path):
    """Behavior-preserving: a normal small project never truncates under the
    generous default budget — the digest is complete and stable."""
    _populate(tmp_path, {"a.py": "x", "pkg/b.py": "y"})
    td = shadow.tree_digest(tmp_path)
    assert td.truncated is False
    assert td.file_count == 2
    assert td.digest.startswith("v1:")


def test_tree_digest_default_budget_does_not_truncate_realistic_project(tmp_path):
    """Realistic project size (300 files) never truncates under default budgets
    (20 000-file / 10 s caps) — the default-non-truncation guarantee holds for
    ordinary project trees, not just the 2-file smoke case."""
    for i in range(300):
        sub = tmp_path / f"pkg{i // 10}"
        sub.mkdir(exist_ok=True)
        (sub / f"module{i}.py").write_text(f"VALUE = {i}\n", encoding="utf-8")
    td = shadow.tree_digest(tmp_path)
    assert td.truncated is False
    assert td.file_count == 300
    assert td.digest.startswith("v1:")


def test_run_shadow_pass_signals_digest_truncation(tmp_path, monkeypatch):
    """When the [CL] digest truncates, run_shadow_pass emits a finding, sets
    ``digest_truncated``, and leaves the stored baseline untouched (no false
    re-baseline on the next complete run)."""
    if not shadow.git_available():
        import pytest

        pytest.skip("git not available")
    monkeypatch.setattr(shadow, "_SHADOW_GIT_ROOT", tmp_path / "sot-git")
    monkeypatch.setattr(shadow, "_SETUP_DIR", tmp_path / "sot-setup")
    _populate(tmp_path, {"a.txt": "1", "b.txt": "2"})

    drift_state = {"project_digest": "v1:PRIOR"}
    # Force tree_digest to report truncation regardless of tree size.
    monkeypatch.setattr(
        shadow,
        "tree_digest",
        lambda *a, **k: shadow.TreeDigest(
            digest="v1:PARTIAL", skipped_symlinks=[], file_count=0, truncated=True
        ),
    )
    summary = shadow.run_shadow_pass("proj-trunc", tmp_path, drift_state)
    assert summary["digest_truncated"] is True
    assert any(f.get("finding_type") == "FRICTION" for f in summary["findings"])
    # Baseline must NOT be overwritten by the partial digest.
    assert drift_state["project_digest"] == "v1:PRIOR"


# --------------------------------------------------------------------------- #
# R2 — discovery scan wall-time budget (complements the existing max_dirs)
# --------------------------------------------------------------------------- #


def test_scan_budget_dir_count_exceeded():
    budget = dp._ScanBudget(max_dirs=2, max_seconds=0)
    assert budget.exceeded(1) is False
    assert budget.exceeded(2) is True
    assert budget.truncated is True
    assert budget.reason == "max_dirs"


def test_scan_budget_wall_time_exceeded(monkeypatch):
    # construct at t=100 (deadline=105); check at t=200 → wall-time exceeded.
    monkeypatch.setattr(dp, "time", _Clock([100.0, 200.0]))
    budget = dp._ScanBudget(max_dirs=10000, max_seconds=5.0)
    assert budget.exceeded(0) is True
    assert budget.truncated is True
    assert budget.reason == "wall_time"


def test_pruned_walk_stops_on_wall_time_budget(tmp_path, monkeypatch, capsys):
    _populate(tmp_path, {"pkg/a.txt": "1", "pkg/sub/b.txt": "2"})
    monkeypatch.setattr(dp, "time", _Clock([100.0, 200.0]))
    budget = dp._ScanBudget(max_dirs=10000, max_seconds=5.0)
    yielded = list(dp._pruned_walk(tmp_path, budget))
    assert yielded == []  # deadline already past → nothing scanned
    assert budget.truncated is True
    assert "wall-time budget" in capsys.readouterr().err


def test_discover_candidates_sets_budget_truncated(tmp_path, monkeypatch):
    """A blown budget during _discover_candidates is observable on the shared
    budget object the caller passed in (→ engine JSON budget_truncated)."""
    _populate(tmp_path, {"pkg/pyproject.toml": "[x]\n"})
    monkeypatch.setattr(dp, "time", _Clock([100.0, 200.0]))
    budget = dp._ScanBudget(max_dirs=10000, max_seconds=5.0)
    dp._discover_candidates(tmp_path, budget)
    assert budget.truncated is True


# --------------------------------------------------------------------------- #
# R4 — verify --strict exit codes (OBS-SOT-1)
# --------------------------------------------------------------------------- #


def test_verdict_exit_code_strict_fail_is_nonzero():
    assert verify._verdict_exit_code({"verdict": "FAIL"}, strict=True) == 1


def test_verdict_exit_code_strict_pass_and_conditional_are_zero():
    assert verify._verdict_exit_code({"verdict": "PASS"}, strict=True) == 0
    assert verify._verdict_exit_code({"verdict": "CONDITIONAL"}, strict=True) == 0


def test_verdict_exit_code_default_fail_is_zero():
    """Default (no --strict): a FAIL still exits 0 — behavior preserved."""
    assert verify._verdict_exit_code({"verdict": "FAIL"}, strict=False) == 0


def _malformed_registry(tmp_path) -> Path:
    sot = tmp_path / ".sot"
    sot.mkdir()
    reg = sot / "registry.yaml"
    reg.write_text("entries: [unterminated\n", encoding="utf-8")  # invalid YAML
    return reg


def test_cmd_run_strict_returns_nonzero_on_fail(tmp_path):
    """End-to-end: a FAIL verdict (S3 YAML-parse) exits 1 under --strict and 0
    by default — proving the exit code is wired at a real return point."""
    reg = _malformed_registry(tmp_path)

    args_default = SimpleNamespace(registry=str(reg), as_json=True, strict=False)
    with redirect_stdout(io.StringIO()) as buf:
        rc_default = verify.cmd_run(args_default)
    assert rc_default == 0
    assert json.loads(buf.getvalue())["verdict"] == "FAIL"

    args_strict = SimpleNamespace(registry=str(reg), as_json=True, strict=True)
    with redirect_stdout(io.StringIO()):
        rc_strict = verify.cmd_run(args_strict)
    assert rc_strict == 1


def test_cmd_run_strict_missing_registry_exits_nonzero(tmp_path):
    """--strict is fail-closed: no verdict produced (missing registry) exits 1.
    Default (non-strict) path still exits 0 when no registry is found."""
    missing = str(tmp_path / "no" / "registry.yaml")

    args_default = SimpleNamespace(registry=missing, strict=False, as_json=False)
    with redirect_stdout(io.StringIO()):
        rc_default = verify.cmd_run(args_default)
    assert rc_default == 0

    args_strict = SimpleNamespace(registry=missing, strict=True, as_json=False)
    with redirect_stdout(io.StringIO()):
        rc_strict = verify.cmd_run(args_strict)
    assert rc_strict == 1

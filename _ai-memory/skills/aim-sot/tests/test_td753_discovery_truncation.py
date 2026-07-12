"""TD-753: discovery must not truncate SILENTLY, and the default skip-set must
spend the budget on real source dirs.

Two levers (TD-753 itself raises no budget — it only adds the warning
and narrows the skip-set; the dir-count default is set elsewhere and is
currently 15000):
  (a) a prominent truncation warning naming the dirs scanned, which budget
      tripped, and the exact env knob to raise it;
  (b) a narrowed default skip-set (generic build / cache / tool trees) so the
      wall-time budget is not burnt walking junk.

Run targeted only:
    pytest tests/test_td753_discovery_truncation.py
"""

import importlib.util
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dp = _load("aim_sot_detect_propose")


def test_max_dirs_truncation_warning_is_prominent(tmp_path, capsys):
    """Forcing the dir-count budget emits a warning naming the count + knob."""
    for i in range(5):
        (tmp_path / f"d{i}").mkdir()

    budget = dp._ScanBudget(max_dirs=1, max_seconds=0)
    list(dp._pruned_walk(tmp_path, budget=budget))

    err = capsys.readouterr().err
    assert "TRUNCATED" in err
    assert "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS" in err, "must name the exact env knob"
    assert "directories" in err
    assert budget.truncated and budget.reason == "max_dirs"


def test_wall_time_truncation_warning_names_seconds_knob(tmp_path, capsys):
    """Forcing the wall-time budget names the seconds knob, not the dirs knob."""
    for i in range(3):
        (tmp_path / f"d{i}").mkdir()

    # A deadline already in the past → first exceeded() check trips wall_time.
    budget = dp._ScanBudget(max_dirs=0, max_seconds=0)
    budget._deadline = -1.0  # force an elapsed deadline deterministically
    budget.max_seconds = 6.0
    list(dp._pruned_walk(tmp_path, budget=budget))

    err = capsys.readouterr().err
    assert "TRUNCATED" in err
    assert "AI_MEMORY_SOT_DISCOVERY_MAX_SECONDS" in err
    assert budget.reason == "wall_time"


def test_no_warning_when_within_budget(tmp_path, capsys):
    (tmp_path / "src").mkdir()
    list(dp._pruned_walk(tmp_path, budget=dp._ScanBudget()))
    assert "TRUNCATED" not in capsys.readouterr().err


def test_default_skipset_prunes_generic_junk_trees(tmp_path):
    """Generic build / cache / tool trees are pruned by default so the budget is
    spent on real source (TD-753)."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x", encoding="utf-8")
    junk = [
        ".next",
        ".gradle",
        "target",
        ".pytest_cache",
        ".turbo",
        ".gemini",
        "coverage",
    ]
    for name in junk:
        (tmp_path / name).mkdir()
        (tmp_path / name / "f.py").write_text("x", encoding="utf-8")

    walked = {p.name for p, _dns, _fns in dp._pruned_walk(tmp_path)}
    assert "src" in walked
    for name in junk:
        assert name not in walked, f"{name} should be pruned by the default skip-set"


def test_vendor_not_hardcoded(tmp_path):
    """`vendor/` is intentionally left to the registry exclude config, not the
    default skip-set (R3/BP-049) — regression guard for the design decision."""
    assert "vendor" not in dp._SKIP_DIRS

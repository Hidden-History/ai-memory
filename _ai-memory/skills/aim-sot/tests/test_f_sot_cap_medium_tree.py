"""The default discovery budget must survive a medium-size project tree
(~2700 directories) walked 3 times cumulatively, without tripping the
directory-count cap.

The discovery scan's directory-count budget is spent cumulatively across the
3 walks that share one `_ScanBudget` (manifests + ADR dirs + nested source
dirs), rather than reset per walk. A cap sized for a single walk therefore
under-covers a medium-size tree by ~3x once shared across all 3 walks, so a
~2600-2800-dir project would truncate discovery partway through. This test
guards against that regression.

This test builds its tree under pytest's `tmp_path` (a fast, local
filesystem), so it exercises only the directory-count cap above — not the
separate wall-time budget, which has its own pre-existing truncation path
for slow filesystems and is out of scope here.

Run targeted only:
    pytest tests/test_f_sot_cap_medium_tree.py
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


def _build_medium_tree(
    root: Path, top_dirs: int = 900, subdirs_per_top: int = 2
) -> int:
    """Create ``top_dirs`` top-level dirs, each with ``subdirs_per_top`` nested
    subdirs. Returns the directory count (including ``root``) that a single
    ``os.walk`` over ``root`` visits."""
    count = 1  # root
    for i in range(top_dirs):
        top = root / f"pkg{i}"
        top.mkdir()
        count += 1
        for j in range(subdirs_per_top):
            (top / f"sub{j}").mkdir()
            count += 1
    return count


def test_default_budget_survives_medium_tree_three_walks(tmp_path, capsys):
    """A ~2700-dir tree, walked 3x cumulatively (manifests + ADR + nested-source
    scanners sharing one budget via `_discover_candidates`), must NOT truncate
    under the real default budget."""
    dirs_per_walk = _build_medium_tree(tmp_path)
    assert (
        2600 <= dirs_per_walk <= 2800
    ), "tree scale must match the coverage-loss report"

    budget = dp._ScanBudget()  # real module default, no synthetic override
    dp._discover_candidates(tmp_path, budget)

    assert budget.truncated is False, (
        f"discovery truncated at {budget.visited} dirs against a "
        f"{budget.max_dirs}-dir cap; expected the 3-walk pass "
        f"({3 * dirs_per_walk} cumulative dirs) to fit"
    )
    assert "TRUNCATED" not in capsys.readouterr().err

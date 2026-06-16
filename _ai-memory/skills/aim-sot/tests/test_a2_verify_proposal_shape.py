"""A2: verify --proposal must flag a wrong-shape proposal, not verify silently.

A proposal mapping that lacks an 'entries' key previously fell through to
``data.get("entries", [])`` → an empty entry set → a spurious pass-on-nothing
that hides the malformed input. It must now be flagged explicitly (graceful, no
traceback), while a well-formed proposal still loads and an explicit empty list
remains valid.

Run targeted only:
    pytest tests/test_a2_verify_proposal_shape.py
"""

import importlib.util
import json
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


verify = _load("aim_sot_verify")


def test_missing_entries_key_is_flagged(tmp_path, capsys):
    """PRE-FIX FAILING: a mapping without 'entries' must error (ec=1), not ec=0/[]."""
    p = tmp_path / "prop.json"
    p.write_text(json.dumps({"items": [{"id": "A"}]}), encoding="utf-8")

    entries, ec = verify._load_proposal(p)

    assert ec == 1, "wrong-shape proposal must return a fatal exit code"
    assert entries == []
    err = capsys.readouterr().err
    assert "entries" in err.lower(), "error message must name the missing 'entries' key"


def test_wellformed_proposal_still_loads(tmp_path):
    p = tmp_path / "prop.json"
    p.write_text(json.dumps({"entries": [{"id": "A"}, {"id": "B"}]}), encoding="utf-8")

    entries, ec = verify._load_proposal(p)

    assert ec == 0
    assert entries == [{"id": "A"}, {"id": "B"}]


def test_explicit_empty_entries_is_valid(tmp_path):
    """An explicit empty list is a legitimate (empty) proposal, distinct from a
    missing key — it must still load cleanly."""
    p = tmp_path / "prop.json"
    p.write_text(json.dumps({"entries": []}), encoding="utf-8")

    entries, ec = verify._load_proposal(p)

    assert ec == 0
    assert entries == []

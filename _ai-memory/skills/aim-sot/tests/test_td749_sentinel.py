"""TD-749: verify must FAIL an entry whose free-text field still carries the
promote sentinel (``TODO(human): …``).

The sentinel is a non-empty string, so it satisfies S1's required/type/non-empty
checks and a partially-filled promote previously verified CONDITIONAL with zero
failures (PM #371). ``_check_S1`` now fails any free-text (non-enum) string field
still holding the marker — including the OPTIONAL ``provenance_note`` — while a
fully-filled entry still passes. The marker literal is single-sourced from
``aim_sot_detect_propose.SENTINEL_MARKER`` (producer and verifier cannot drift).

Run targeted only:
    pytest tests/test_td749_sentinel.py
"""

import importlib.util
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


verify = _load("aim_sot_verify")
dp = _load("aim_sot_detect_propose")
_SC = verify._load_schema_constraints()


def _filled_entry(**overrides):
    """A fully-filled, S1-clean entry."""
    entry = {
        "id": "svc-a",
        "kind": "service",
        "boundary_type": "component",
        "sot_location": "svc-a/",
        "owner": "platform-team",
        "description": "The A service.",
        "last_verified": "2026-07-01",
        "added_by": "amelia",
        "provenance_note": "Added during bootstrap.",
        "status": "proposed",
    }
    entry.update(overrides)
    return entry


def test_single_sourced_marker_matches_producer():
    """The verifier's marker is the SAME object the producer emits — no drift."""
    assert verify._SENTINEL_MARKER == dp.SENTINEL_MARKER == "TODO(human):"


def test_filled_entry_passes_s1():
    failures, _ = verify._check_S1([_filled_entry()], _SC)
    assert failures == [], f"a fully-filled entry must pass S1, got {failures}"


def test_required_free_text_sentinels_fail():
    """owner + description (required free-text) sentinels must FAIL."""
    entry = _filled_entry(
        owner=f"{dp.SENTINEL_MARKER} <owning team or person>",
        description=f"{dp.SENTINEL_MARKER} <one-line summary of this boundary>",
    )
    failures, _ = verify._check_S1([entry], _SC)
    failed_fields = {f["detail"].split("'")[1] for f in failures}
    assert "owner" in failed_fields
    assert "description" in failed_fields
    assert all(f["check"] == "S1" for f in failures)
    assert all("TODO(human):" in f["detail"] for f in failures)


def test_optional_provenance_note_sentinel_fails():
    """The OPTIONAL provenance_note is not in S1's required loop — the sentinel
    scan must still catch it (this is the field the required-only loop would
    miss)."""
    entry = _filled_entry(
        provenance_note=f"{dp.SENTINEL_MARKER} <how/why this entry was added>"
    )
    failures, _ = verify._check_S1([entry], _SC)
    failed_fields = {f["detail"].split("'")[1] for f in failures}
    assert (
        "provenance_note" in failed_fields
    ), "optional free-text sentinel must FAIL even though it is not required"


def test_enum_field_sentinel_not_double_flagged_by_s1():
    """A sentinel in the enum field `kind` is S4's responsibility — S1 must NOT
    also flag it (enum fields are excluded from the free-text scan)."""
    entry = _filled_entry(kind=f"{dp.SENTINEL_MARKER} <service|library>")
    failures, _ = verify._check_S1([entry], _SC)
    assert not any(f["detail"].startswith("Field 'kind'") for f in failures)


def test_producer_output_fails_verification():
    """End-to-end: the exact placeholders the producer emits are caught."""
    entry = _filled_entry(
        owner=f"{dp.SENTINEL_MARKER} <owning team or person>",
        description=f"{dp.SENTINEL_MARKER} <one-line summary of this boundary>",
        provenance_note=f"{dp.SENTINEL_MARKER} <how/why this entry was added>",
    )
    failures, _ = verify._check_S1([entry], _SC)
    failed_fields = {f["detail"].split("'")[1] for f in failures}
    assert {"owner", "description", "provenance_note"} <= failed_fields

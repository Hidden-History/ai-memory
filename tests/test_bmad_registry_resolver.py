"""Absent-registry arm of BMAD skill resolution (Story 1.4, AC-2 and AC-4).

The registry is BMAD's, at BMAD's path, and is read but never written. Its
absence is not an error condition to recover from: it is the state of every
install without BMAD, and it must be reportable as such — distinctly from a
registry that is present and carries no rows.

Synthetic identifiers only. Fixtures build their own registry; none of them
names a live BMAD skill, module or agent (AD-20b).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory.bmad_registry import (
    INDETERMINATE,
    REGISTRY_RELATIVE_PATH,
    RESOLVED,
    UNAVAILABLE,
    registry_path,
    resolve,
    resolve_registry,
)

HEADER = "module,skill,display-name,menu-code"


def _write_registry(workspace: Path, body: str) -> Path:
    target = registry_path(workspace)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# AC-4 — absent is not empty
# ---------------------------------------------------------------------------


def test_absent_registry_resolves_to_the_bare_token(tmp_path: Path) -> None:
    """The token is bare: unqualified, on its own axis, exactly as AC-4 writes it."""
    result = resolve(tmp_path)
    assert result.status == UNAVAILABLE
    assert result.status == "unavailable"
    assert result.rows == ()
    assert result.is_empty_roster is False
    assert result.detail is not None


def test_present_but_empty_registry_is_an_empty_roster_not_unavailable(
    tmp_path: Path,
) -> None:
    """The other direction of the pair: a header with no rows is a result."""
    _write_registry(tmp_path, f"{HEADER}\n")
    result = resolve(tmp_path)
    assert result.status == RESOLVED
    assert result.rows == ()
    assert result.is_empty_roster is True
    assert result.columns == tuple(HEADER.split(","))


def test_absent_and_empty_are_distinguishable(tmp_path: Path) -> None:
    """A consumer must be able to tell 'none declared' from 'declared and not found'."""
    absent = resolve(tmp_path)
    _write_registry(tmp_path, f"{HEADER}\n")
    empty = resolve(tmp_path)
    assert absent.status != empty.status
    assert absent.is_empty_roster != empty.is_empty_roster


def test_populated_registry_resolves_its_rows(tmp_path: Path) -> None:
    _write_registry(
        tmp_path, f"{HEADER}\nsynthetic-module,synthetic-skill,Synthetic Skill,SS\n"
    )
    result = resolve(tmp_path)
    assert result.status == RESOLVED
    assert len(result.rows) == 1
    assert result.rows[0]["skill"] == "synthetic-skill"
    assert result.excluded == ()


def test_unreadable_registry_is_indeterminate_not_absent(tmp_path: Path) -> None:
    """An unresolved upstream state fails open and is counted, never folded into absent."""
    target = _write_registry(tmp_path, f"{HEADER}\n")
    target.chmod(0o000)
    try:
        result = resolve(tmp_path)
    finally:
        target.chmod(0o644)
    if result.status == RESOLVED:
        pytest.skip("filesystem does not enforce mode bits for this user")
    assert result.status == INDETERMINATE
    assert result.status != UNAVAILABLE


def test_headerless_registry_is_indeterminate(tmp_path: Path) -> None:
    _write_registry(tmp_path, "")
    result = resolve(tmp_path)
    assert result.status == INDETERMINATE


# ---------------------------------------------------------------------------
# AD-6 — per-column validation, per-field exclusion
# ---------------------------------------------------------------------------


def test_short_row_loses_only_the_missing_field(tmp_path: Path) -> None:
    """A validator that drops a whole row on one bad column is a defect."""
    _write_registry(tmp_path, f"{HEADER}\nsynthetic-module,synthetic-skill\n")
    result = resolve(tmp_path)
    assert result.status == RESOLVED
    assert len(result.rows) == 1
    assert result.rows[0]["module"] == "synthetic-module"
    assert result.rows[0]["skill"] == "synthetic-skill"
    excluded = {e.column for e in result.excluded}
    assert excluded == {"display-name", "menu-code"}


def test_overlong_row_keeps_its_declared_columns(tmp_path: Path) -> None:
    _write_registry(
        tmp_path,
        f"{HEADER}\nsynthetic-module,synthetic-skill,Synthetic Skill,SS,spill-one,spill-two\n",
    )
    result = resolve(tmp_path)
    assert result.status == RESOLVED
    assert len(result.rows) == 1
    assert set(result.rows[0]) == set(HEADER.split(","))
    assert any("more fields than the header" in e.reason for e in result.excluded)


def test_a_bad_row_does_not_cost_a_good_one(tmp_path: Path) -> None:
    _write_registry(
        tmp_path,
        f"{HEADER}\nsynthetic-module,synthetic-a\nsynthetic-module,synthetic-b,Synthetic B,SB\n",
    )
    result = resolve(tmp_path)
    assert [r["skill"] for r in result.rows] == ["synthetic-a", "synthetic-b"]


def test_embedded_delimiter_is_parsed_not_split(tmp_path: Path) -> None:
    """A quoted comma is one field; a delimiter split would silently shift the row."""
    _write_registry(
        tmp_path,
        f'{HEADER}\nsynthetic-module,synthetic-skill,"Synthetic, Skill",SS\n',
    )
    result = resolve(tmp_path)
    assert result.rows[0]["display-name"] == "Synthetic, Skill"
    assert result.rows[0]["menu-code"] == "SS"


# ---------------------------------------------------------------------------
# AC-2 — nothing about the degraded state is cached
# ---------------------------------------------------------------------------


def test_bmad_installed_afterwards_works_with_no_reinstall(tmp_path: Path) -> None:
    """Detection is at call time: the same process sees BMAD appear."""
    first = resolve(tmp_path)
    assert first.status == UNAVAILABLE

    _write_registry(
        tmp_path, f"{HEADER}\nsynthetic-module,synthetic-skill,Synthetic Skill,SS\n"
    )

    second = resolve(tmp_path)
    assert second.status == RESOLVED
    assert len(second.rows) == 1


def test_removing_bmad_returns_to_unavailable_in_the_same_process(
    tmp_path: Path,
) -> None:
    """The other direction: no stale 'present' flag survives the dependency going away."""
    target = _write_registry(tmp_path, f"{HEADER}\n")
    assert resolve(tmp_path).status == RESOLVED
    target.unlink()
    assert resolve(tmp_path).status == UNAVAILABLE


def test_module_holds_no_resolution_state() -> None:
    """A cache is what AC-2 forbids; there is nothing here to hold one."""
    import memory.bmad_registry as module

    mutable = [
        name
        for name, value in vars(module).items()
        if not name.startswith("__")
        and isinstance(value, (dict, list, set))
        and not isinstance(value, type)
    ]
    assert mutable == []


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def test_registry_path_is_resolved_from_the_workspace_root(tmp_path: Path) -> None:
    assert registry_path(tmp_path) == tmp_path / REGISTRY_RELATIVE_PATH


def test_resolve_registry_accepts_a_direct_path(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere.csv"
    target.write_text(f"{HEADER}\n", encoding="utf-8")
    assert resolve_registry(target).status == RESOLVED
    assert resolve_registry(tmp_path / "missing.csv").status == UNAVAILABLE


# ---------------------------------------------------------------------------
# Round 2 — the presence probe must not crash, and must not call an
# indeterminate state absent (AD-24 fails open and counts; AD-6 keeps
# "declared and not found" distinct from "none declared").
# ---------------------------------------------------------------------------


def test_inaccessible_parent_is_indeterminate_not_a_crash(tmp_path: Path) -> None:
    """A non-traversable parent must not escape as PermissionError (AC-1).

    ``Path.exists()`` does not swallow EACCES — it re-raises — so probing
    presence with it turns an unresolved upstream state into an unhandled
    error, which AC-1 forbids in the same sentence as the stack trace.
    """
    target = _write_registry(tmp_path, f"{HEADER}\n")
    target.parent.chmod(0o000)
    try:
        result = resolve(tmp_path)
    finally:
        target.parent.chmod(0o755)
    if result.status == RESOLVED:
        pytest.skip("filesystem does not enforce mode bits for this user")
    assert result.status == INDETERMINATE
    assert result.status != UNAVAILABLE


def test_registry_path_that_is_a_directory_is_indeterminate(tmp_path: Path) -> None:
    """Uid-independent guard on the indeterminate/absent distinction.

    The mode-bit fixtures above both self-skip for a user the filesystem does
    not constrain — root, which is the default in a CI container — so on that
    user they guard nothing. This case reaches the same distinction through a
    path type rather than a permission, and therefore holds for every uid.
    """
    target = registry_path(tmp_path)
    target.mkdir(parents=True)
    result = resolve(tmp_path)
    assert result.status == INDETERMINATE
    assert result.status != UNAVAILABLE


def test_broken_symlink_is_indeterminate_not_absent(tmp_path: Path) -> None:
    """A dangling link is 'declared and not found', not 'none declared' (AD-6)."""
    target = registry_path(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(tmp_path / "no-such-registry.csv")
    result = resolve(tmp_path)
    assert target.is_symlink()
    assert result.status == INDETERMINATE
    assert result.status != UNAVAILABLE


def test_unparseable_csv_is_indeterminate_not_an_exception(tmp_path: Path) -> None:
    """csv raises from the iterator, which sits outside the read's try block."""
    import csv as _csv

    _write_registry(tmp_path, f'{HEADER}\n"' + ("x" * 200_000) + '"\n')
    previous = _csv.field_size_limit(1000)
    try:
        result = resolve(tmp_path)
    finally:
        _csv.field_size_limit(previous)
    assert result.status == INDETERMINATE
    assert result.detail is not None


def test_byte_order_mark_does_not_mangle_the_first_column(tmp_path: Path) -> None:
    """A BOM belongs to the encoding, not to the first column's name."""
    target = registry_path(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\xef\xbb\xbf" + f"{HEADER}\nm,s,D,MC\n".encode())
    result = resolve(tmp_path)
    assert result.status == RESOLVED
    assert result.columns[0] == "module"
    assert result.rows[0]["module"] == "m"


def test_duplicate_header_column_is_excluded_not_silently_dropped(
    tmp_path: Path,
) -> None:
    """A repeated header name costs a field; per AD-6 that must be reported."""
    _write_registry(tmp_path, "module,skill,module\nm1,s1,m2\n")
    result = resolve(tmp_path)
    assert result.status == RESOLVED
    assert [e.column for e in result.excluded] == ["module"]
    assert "duplicate" in result.excluded[0].reason


def test_excluded_field_row_is_the_file_line_it_came_from(tmp_path: Path) -> None:
    """A data ordinal cannot locate the row a reader has to go and look at."""
    _write_registry(tmp_path, f'{HEADER}\n"multi\nline",s,D,MC\nshort\n')
    result = resolve(tmp_path)
    assert result.status == RESOLVED
    short_row_exclusions = [e for e in result.excluded if e.row > 2]
    assert short_row_exclusions, f"no exclusion carries a file line: {result.excluded}"
    assert short_row_exclusions[0].row == 4


def test_module_holds_no_cached_callable(tmp_path: Path) -> None:
    """AC-2 forbids a cache, and the likely form of one is a cached callable.

    The sibling test rejects a module-level container. It does not reject a
    memoised function, which is how a presence probe would realistically be
    cached, so the two run together rather than one standing for both.
    """
    import memory.bmad_registry as module

    cached = [
        name
        for name, value in vars(module).items()
        if not name.startswith("__") and hasattr(value, "cache_clear")
    ]
    assert cached == []

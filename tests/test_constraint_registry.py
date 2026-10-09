"""Tests for the Constraint registry reader.

The reader parses the registry with a CSV parser, validates it per column,
and returns one immutable result. These tests pin that a bad field costs
that field only, and that a registry which could not be read is never
reported as an empty one.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
from pathlib import Path

import pytest

from memory.degraded import ENFORCEMENT_STATES, POV_TREE

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

_DETECTORS_DIR = Path(__file__).resolve().parent.parent / POV_TREE / "detectors"
_REGISTRY_PATH = _DETECTORS_DIR / "constraint_registry.py"

_spec = importlib.util.spec_from_file_location("constraint_registry", _REGISTRY_PATH)
registry = importlib.util.module_from_spec(_spec)
sys.modules["constraint_registry"] = registry
_spec.loader.exec_module(registry)

HEADER = "id,detector,enforcement_state\n"


def _read(tmp_path: Path, text: str, *, raw: bytes | None = None):
    path = tmp_path / "registry.csv"
    if raw is not None:
        path.write_bytes(raw)
    else:
        path.write_text(text, encoding="utf-8")
    return registry.read_registry(path)


def _excluded(result) -> list[tuple[int, str]]:
    return [(item.line, item.column) for item in result.excluded]


# ---------------------------------------------------------------------------
# The four state tokens
# ---------------------------------------------------------------------------


def test_state_tokens_are_one_ordered_tuple_equal_to_the_package_definition() -> None:
    assert isinstance(registry.ENFORCEMENT_STATES, tuple)
    assert registry.ENFORCEMENT_STATES == ENFORCEMENT_STATES


@pytest.mark.parametrize("state", ENFORCEMENT_STATES)
def test_each_of_the_four_states_is_a_valid_marking(tmp_path: Path, state: str) -> None:
    result = _read(tmp_path, HEADER + f"ZZ-01,,{state}\n")

    assert result.status == registry.READ
    assert result.excluded == ()
    assert result.rows[0].values["enforcement_state"] == state


@pytest.mark.parametrize(
    "value",
    [
        "true",
        "false",
        "yes",
        "no",
        "1",
        "0",
        "unenforced",
        "UNENFORCED",
        "Not-Yet-Enforced",
        "not-yet-enforced until the next release",
        " not-yet-enforced",
        " ",
    ],
)
def test_a_marking_that_is_not_one_of_the_four_states_is_excluded(
    tmp_path: Path, value: str
) -> None:
    result = _read(tmp_path, HEADER + f"ZZ-01,,{value}\n")

    assert _excluded(result) == [(2, "enforcement_state")]
    row = result.rows[0]
    assert "enforcement_state" not in row.values
    assert row.failed("enforcement_state").reason


# ---------------------------------------------------------------------------
# Parsed, not split; validated per column, not per row length
# ---------------------------------------------------------------------------


def test_quoted_commas_are_one_field_and_later_columns_do_not_shift(
    tmp_path: Path,
) -> None:
    result = _read(
        tmp_path,
        HEADER + '"ZZ-06","a, quoted, detector",enforced-but-non-blocking\n',
    )

    assert result.excluded == ()
    assert dict(result.rows[0].values) == {
        "id": "ZZ-06",
        "detector": "a, quoted, detector",
        "enforcement_state": "enforced-but-non-blocking",
    }


def test_a_bad_field_is_excluded_and_its_row_is_kept(tmp_path: Path) -> None:
    result = _read(tmp_path, HEADER + "ZZ-01,checks/zz01.py,true\nZZ-02,,\n")

    assert len(result.rows) == 2
    assert _excluded(result) == [(2, "enforcement_state")]
    kept = result.rows[0]
    assert kept.line == 2
    assert dict(kept.values) == {"id": "ZZ-01", "detector": "checks/zz01.py"}
    assert kept.failed("id") is None
    assert kept.failed("detector") is None


def test_an_overflow_field_is_one_exclusion_and_the_row_stays_usable(
    tmp_path: Path,
) -> None:
    result = _read(tmp_path, HEADER + "ZZ-07,,unenforceable,stray,more\n")

    assert _excluded(result) == [(2, registry.OVERFLOW_COLUMN)]
    assert dict(result.rows[0].values) == {
        "id": "ZZ-07",
        "detector": "",
        "enforcement_state": "unenforceable",
    }


def test_an_absent_field_is_a_failure_and_an_empty_field_is_a_value(
    tmp_path: Path,
) -> None:
    result = _read(tmp_path, HEADER + "ZZ-01,\nZZ-02\nZZ-03,,\n")

    assert _excluded(result) == [
        (2, "enforcement_state"),
        (3, "detector"),
        (3, "enforcement_state"),
    ]
    assert "enforcement_state" not in result.rows[0].values
    assert result.rows[0].values["detector"] == ""
    assert result.rows[2].values["enforcement_state"] == ""
    assert result.rows[2].excluded == ()


def test_id_and_detector_are_trimmed_before_they_are_judged(tmp_path: Path) -> None:
    result = _read(tmp_path, HEADER + " ZZ-01 ,  ,\n  ,checks/x.py,\n")

    assert dict(result.rows[0].values) == {
        "id": "ZZ-01",
        "detector": "",
        "enforcement_state": "",
    }
    assert _excluded(result) == [(3, "id")]
    assert result.rows[1].values["detector"] == "checks/x.py"


def test_every_row_sharing_an_id_loses_its_id_and_keeps_its_other_fields(
    tmp_path: Path,
) -> None:
    result = _read(
        tmp_path,
        HEADER + "ZZ-01,checks/a.py,\nZZ-02,,not-yet-enforced\nZZ-01 ,,unenforceable\n",
    )

    assert _excluded(result) == [(2, "id"), (4, "id")]
    assert "line(s) 4" in result.rows[0].failed("id").reason
    assert "line(s) 2" in result.rows[2].failed("id").reason
    assert dict(result.rows[0].values) == {
        "detector": "checks/a.py",
        "enforcement_state": "",
    }
    assert result.rows[1].values["id"] == "ZZ-02"
    assert result.rows[2].values["enforcement_state"] == "unenforceable"


def test_line_numbers_are_file_lines_not_row_ordinals(tmp_path: Path) -> None:
    result = _read(tmp_path, HEADER + "ZZ-01,zz_a.py,\n\n\nZZ-02,,\n")

    assert [row.line for row in result.rows] == [2, 5]


def test_an_unknown_column_is_carried_through_and_not_validated(
    tmp_path: Path,
) -> None:
    result = _read(
        tmp_path,
        "id,fixture,detector,enforcement_state\nZZ-01,anything at all,,\nZZ-02\n",
    )

    assert result.columns == ("id", "fixture", "detector", "enforcement_state")
    assert result.rows[0].values["fixture"] == "anything at all"
    assert result.rows[0].excluded == ()
    # The short row fails its absent required fields only.
    assert _excluded(result) == [(3, "detector"), (3, "enforcement_state")]


def test_a_byte_order_mark_does_not_hide_the_first_column(tmp_path: Path) -> None:
    result = _read(tmp_path, "", raw=b"\xef\xbb\xbf" + HEADER.encode() + b"ZZ-01,,\n")

    assert result.status == registry.READ
    assert result.rows[0].values["id"] == "ZZ-01"


def test_an_undecodable_byte_fails_the_one_field_it_is_in(tmp_path: Path) -> None:
    result = _read(
        tmp_path,
        "",
        raw=HEADER.encode() + b"ZZ-01,checks/\xff.py,not-yet-enforced\n",
    )

    assert _excluded(result) == [(2, "detector")]
    assert dict(result.rows[0].values) == {
        "id": "ZZ-01",
        "enforcement_state": "not-yet-enforced",
    }


# ---------------------------------------------------------------------------
# Empty, and could-not-be-checked, are different results
# ---------------------------------------------------------------------------


def test_header_only_is_an_empty_read(tmp_path: Path) -> None:
    result = _read(tmp_path, HEADER)

    assert result.status == registry.EMPTY
    assert result.rows == ()
    assert result.columns == registry.REQUIRED_COLUMNS


def test_a_missing_file_is_unchecked_and_says_no_file(tmp_path: Path) -> None:
    result = registry.read_registry(tmp_path / "absent.csv")

    assert result.status == registry.UNCHECKED
    assert "no file at" in result.detail
    assert result.rows == ()


def test_an_unreadable_file_is_unchecked_and_says_it_could_not_be_read(
    tmp_path: Path,
) -> None:
    # A directory at the registry's path: reading it raises OSError whatever
    # the test runner's privileges are.
    path = tmp_path / "registry.csv"
    path.mkdir()

    result = registry.read_registry(path)

    assert result.status == registry.UNCHECKED
    assert "could not be read" in result.detail
    assert "no file at" not in result.detail


def test_a_dangling_link_is_unchecked_not_absent(tmp_path: Path) -> None:
    path = tmp_path / "registry.csv"
    path.symlink_to(tmp_path / "nowhere.csv")

    result = registry.read_registry(path)

    assert result.status == registry.UNCHECKED
    assert "could not be read" in result.detail


def test_a_zero_byte_file_is_unchecked_not_empty(tmp_path: Path) -> None:
    result = _read(tmp_path, "")

    assert result.status == registry.UNCHECKED
    assert "no header row" in result.detail


@pytest.mark.parametrize(
    ("header", "named"),
    [
        ("id,detector\n", "enforcement_state"),
        ("id,enforcement_state\n", "detector"),
        ("detector,enforcement_state\n", "id"),
        ("ID,detector,enforcement_state\n", "id"),
        ("name,owner\n", "id, detector, enforcement_state"),
    ],
)
def test_a_header_missing_a_required_column_is_unchecked_and_names_it(
    tmp_path: Path, header: str, named: str
) -> None:
    result = _read(tmp_path, header + "ZZ-01,,\n")

    assert result.status == registry.UNCHECKED
    assert result.detail.endswith(f"missing required column(s): {named}")
    assert result.rows == ()


def test_a_header_declaring_a_required_column_twice_is_unchecked(
    tmp_path: Path,
) -> None:
    result = _read(tmp_path, "id,detector,detector,enforcement_state\nZZ-01,a.py,,\n")

    assert result.status == registry.UNCHECKED
    assert result.detail.endswith("more than once: detector")


def test_a_parse_error_is_unchecked_not_empty(tmp_path: Path) -> None:
    # The csv module refuses a field longer than its limit; that is the
    # csv.Error path, reached without depending on the Python version.
    result = _read(tmp_path, HEADER + "ZZ-01," + "x" * 200_000 + ",\n")

    assert result.status == registry.UNCHECKED
    assert "could not be parsed" in result.detail


def test_a_quote_that_is_never_closed_is_unchecked_and_hides_no_row(
    tmp_path: Path,
) -> None:
    # A lenient parser lets the open quote take every later line into one
    # field: the two rows after it would never be seen, and one row is read.
    result = _read(tmp_path, HEADER + 'ZZ-01,checks/a.py,"\nZZ-02,,\nZZ-03,,true\n')

    assert result.status == registry.UNCHECKED
    assert "could not be parsed" in result.detail
    assert result.rows == ()


# ---------------------------------------------------------------------------
# A cell may not hold a line break
# ---------------------------------------------------------------------------

_NOTE_HEADER = b"id,detector,enforcement_state,note\n"

#: A registry holding a line break in one cell, and the file line its record
#: ends on.
_LINE_BREAK_IN_A_CELL = {
    "a quoted line feed": (
        HEADER.encode() + b'ZZ-01,"zz one\nzz two",\nZZ-02,,\n',
        3,
    ),
    "a quoted carriage return": (
        HEADER.encode() + b'ZZ-01,"zz one\rzz two",\nZZ-02,,\n',
        3,
    ),
    "a quoted carriage return and line feed": (
        HEADER.encode() + b'ZZ-01,"zz one\r\nzz two",\nZZ-02,,\n',
        3,
    ),
    "a header cell": (
        b'id,detector,enforcement_state,"zz\nnote"\nZZ-01,,,\n',
        2,
    ),
    "a column no check reads": (
        _NOTE_HEADER + b'ZZ-01,zz_a.py,,\nZZ-02,,,"zz one\nzz two"\n',
        4,
    ),
    "a cell beyond the header's width": (
        HEADER.encode() + b'ZZ-01,zz_a.py,,"zz one\nzz two"\n',
        3,
    ),
    "the earlier of two cells under one repeated name": (
        b"id,note,detector,enforcement_state,note\n"
        b'ZZ-01,"zz one\nzz two",zz_a.py,,zz three\n',
        3,
    ),
}


@pytest.mark.parametrize("case", sorted(_LINE_BREAK_IN_A_CELL))
def test_a_line_break_in_any_cell_makes_the_registry_unchecked(
    tmp_path: Path, case: str
) -> None:
    raw, line = _LINE_BREAK_IN_A_CELL[case]

    result = _read(tmp_path, "", raw=raw)

    assert result.status == registry.UNCHECKED
    assert result.rows == ()
    assert result.excluded == ()
    assert result.detail.endswith(
        f"holds a line break inside a cell, in the record that ends on line {line}; "
        "a registry cell must sit on one line"
    )


def test_a_carriage_return_outside_quotes_ends_a_row_as_before(
    tmp_path: Path,
) -> None:
    result = _read(tmp_path, "", raw=HEADER.encode() + b"ZZ-01,zz_a.py,\rZZ-02,,\n")

    assert result.status == registry.READ
    assert [(row.line, row.values["id"]) for row in result.rows] == [
        (2, "ZZ-01"),
        (3, "ZZ-02"),
    ]


@pytest.mark.parametrize("char", ["\u2028", "\x0b", "\x0c", "\x85", "\x1b"])
def test_a_character_that_does_not_end_a_line_for_the_parser_stays_in_its_cell(
    tmp_path: Path, char: str
) -> None:
    """Only a line feed is a line break here; these are escaped on output."""
    result = _read(tmp_path, HEADER + f'ZZ-01,"zz{char}one.py",\nZZ-02,,\n')

    assert result.status == registry.READ
    assert [row.line for row in result.rows] == [2, 3]
    assert result.rows[0].values["detector"] == f"zz{char}one.py"


def test_a_line_break_in_a_header_cell_is_reported_before_a_missing_column(
    tmp_path: Path,
) -> None:
    """The broken cell is why the column is missing, so it is what is named."""
    result = _read(tmp_path, 'id,"dete\nctor",enforcement_state\nZZ-01,,\n')

    assert result.status == registry.UNCHECKED
    assert "holds a line break inside a cell" in result.detail
    assert "ends on line 2;" in result.detail
    assert "missing required column" not in result.detail


def test_a_header_defect_is_reported_before_a_line_break_in_a_row(
    tmp_path: Path,
) -> None:
    result = _read(tmp_path, 'id,detector\nZZ-01,"zz one\nzz two"\n')

    assert result.status == registry.UNCHECKED
    assert result.detail.endswith("missing required column(s): enforcement_state")


def test_a_line_break_is_reported_before_a_parse_error_in_a_later_record(
    tmp_path: Path,
) -> None:
    """The file is read in order, and the first of the two ends the read."""
    broken_then_unclosed = HEADER + 'ZZ-01,"zz one\nzz two",\nZZ-02,zz_a.py,"\n'
    unclosed_only = HEADER + "ZZ-01,zz_b.py,\n" + 'ZZ-02,zz_a.py,"\n'

    first = _read(tmp_path, broken_then_unclosed)
    second = _read(tmp_path, unclosed_only)

    assert first.status == registry.UNCHECKED
    assert "holds a line break inside a cell" in first.detail
    assert "ends on line 3;" in first.detail
    assert second.status == registry.UNCHECKED
    assert "could not be parsed" in second.detail
    assert "line break" not in second.detail


def test_rows_between_an_opening_quote_and_a_stray_one_are_not_dropped_silently(
    tmp_path: Path,
) -> None:
    """Read leniently, lines 3 and 4 vanish into one cell and two rows are read."""
    result = _read(
        tmp_path,
        _NOTE_HEADER.decode() + 'ZZ-01,,not-yet-enforced,"zz note\n'
        "ZZ-02,zz_gone.py,enforced-and-blocking,\n"
        'ZZ-03,,,"\n'
        "ZZ-04,,unenforceable,\n",
    )

    assert result.status == registry.UNCHECKED
    assert result.rows == ()
    assert "ends on line 4;" in result.detail


# ---------------------------------------------------------------------------
# The result is immutable
# ---------------------------------------------------------------------------


def test_the_result_cannot_be_mutated(tmp_path: Path) -> None:
    result = _read(tmp_path, HEADER + "ZZ-01,,\n")

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.status = registry.EMPTY
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.rows[0].line = 9
    with pytest.raises(TypeError):
        result.rows[0].values["detector"] = "checks/late.py"

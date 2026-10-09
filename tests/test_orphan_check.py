"""Tests for the orphan check.

The check reads one Constraint registry and refuses, with a non-zero exit,
when a Constraint has neither a Detector nor a valid marking. These tests
run it as a command, and assert on both what it prints and how it exits.

Every registry here is built on ``tmp_path`` with synthetic identifiers.
"""

from __future__ import annotations

import csv
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from memory.degraded import POV_TREE

# ---------------------------------------------------------------------------
# Module loading: the reader first, so the check's sibling import resolves
# ---------------------------------------------------------------------------

_DETECTORS_DIR = Path(__file__).resolve().parent.parent / POV_TREE / "detectors"
_REGISTRY_MODULE = _DETECTORS_DIR / "constraint_registry.py"
_CHECK = _DETECTORS_DIR / "orphan_check.py"
_SHIPPED_REGISTRY = _DETECTORS_DIR / "constraint-registry.csv"
_FIXTURE_PAIR = _DETECTORS_DIR / "fixtures" / "orphan_check"

_rspec = importlib.util.spec_from_file_location("constraint_registry", _REGISTRY_MODULE)
registry = importlib.util.module_from_spec(_rspec)
sys.modules["constraint_registry"] = registry
_rspec.loader.exec_module(registry)

_cspec = importlib.util.spec_from_file_location("orphan_check", _CHECK)
orphan_check = importlib.util.module_from_spec(_cspec)
sys.modules["orphan_check"] = orphan_check
_cspec.loader.exec_module(orphan_check)

HEADER = "id,detector,enforcement_state\n"

WORKED_EXAMPLE = (
    HEADER + "ZZ-01,checks/zz01.py,\n"
    "ZZ-02,,not-yet-enforced\n"
    "ZZ-03,,\n"
    "ZZ-04,,true\n"
    "ZZ-05,,enforced-and-blocking\n"
    '"ZZ-06","a, quoted, detector",enforced-but-non-blocking\n'
    "ZZ-07,,unenforceable,stray\n"
    "ZZ-08, ,\n"
)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "registry.csv"
    path.write_text(text, encoding="utf-8")
    return path


def _run(*args: str, check: Path = _CHECK) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(check), *args], capture_output=True, text=True
    )


def _check(tmp_path: Path, text: str) -> subprocess.CompletedProcess[str]:
    return _run("--registry", str(_write(tmp_path, text)))


def _findings(out: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith("finding:")]


def _exclusions(out: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith("exclusion:")]


def _dispositions(tmp_path: Path, text: str) -> list[str]:
    read = registry.read_registry(_write(tmp_path, text))
    return [orphan_check.row_disposition(row).token for row in read.rows]


# ---------------------------------------------------------------------------
# The fixture pair: one registry the check must flag, one it must not
# ---------------------------------------------------------------------------


def test_fixture_pair_a_row_with_no_detector_and_no_marking_is_flagged() -> None:
    result = _run("--registry", str(_FIXTURE_PAIR / "positive.csv"))

    assert result.returncode == 1
    assert _findings(result.stdout) == [
        "finding: line 3: ZZ-02: orphan - "
        "no Detector and no Enforcement state is declared"
    ]
    assert "clean:" not in result.stdout


def test_fixture_pair_the_same_row_with_a_marking_is_not_flagged() -> None:
    result = _run("--registry", str(_FIXTURE_PAIR / "negative.csv"))

    assert result.returncode == 0
    assert _findings(result.stdout) == []
    assert result.stdout.startswith("clean:constraint-registry - 2 row(s) of ")


def test_a_detector_cell_holding_only_spaces_is_an_orphan_not_bound(
    tmp_path: Path,
) -> None:
    result = _check(tmp_path, HEADER + "ZZ-08,   ,\n")

    assert result.returncode == 1
    assert _findings(result.stdout)[0].startswith("finding: line 2: ZZ-08: orphan - ")


def test_a_row_with_a_detector_declared_is_not_flagged(tmp_path: Path) -> None:
    result = _check(tmp_path, HEADER + "ZZ-01,checks/zz01.py,\n")

    assert result.returncode == 0
    assert _findings(result.stdout) == []
    assert result.stdout.startswith("clean:constraint-registry - ")


# ---------------------------------------------------------------------------
# A marking is one of the four states, or it is refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state", ["unenforceable", "not-yet-enforced"])
def test_a_state_without_a_working_detector_is_accepted_as_a_marking(
    tmp_path: Path, state: str
) -> None:
    assert _dispositions(tmp_path, HEADER + f"ZZ-01,,{state}\n") == [f"marked:{state}"]

    result = _run("--registry", str(tmp_path / "registry.csv"))
    assert result.returncode == 0
    assert _findings(result.stdout) == []


@pytest.mark.parametrize(
    "state", ["enforced-but-non-blocking", "enforced-and-blocking"]
)
def test_a_state_with_a_working_detector_is_accepted_beside_a_detector(
    tmp_path: Path, state: str
) -> None:
    result = _check(tmp_path, HEADER + f"ZZ-01,checks/zz01.py,{state}\n")

    assert result.returncode == 0
    assert _findings(result.stdout) == []
    assert _exclusions(result.stdout) == []


@pytest.mark.parametrize(
    "state", ["enforced-but-non-blocking", "enforced-and-blocking"]
)
def test_a_state_claiming_a_working_detector_with_none_declared_is_refused(
    tmp_path: Path, state: str
) -> None:
    result = _check(tmp_path, HEADER + f"ZZ-05,,{state}\n")

    assert result.returncode == 1
    assert _findings(result.stdout) == [
        "finding: line 2: ZZ-05: refused:enforcement_state - "
        f"column enforcement_state: '{state}' claims a working Detector "
        "and no Detector is declared"
    ]


@pytest.mark.parametrize(
    "value",
    [
        "true",
        "false",
        "unenforced",
        "UNENFORCED",
        "yes",
        "1",
        "not-yet-enforced for now",
    ],
)
def test_a_marking_that_does_not_name_one_of_the_four_states_is_refused(
    tmp_path: Path, value: str
) -> None:
    result = _check(tmp_path, HEADER + f"ZZ-04,,{value}\n")

    assert result.returncode == 1
    assert _findings(result.stdout) == [
        "finding: line 2: ZZ-04: refused:enforcement_state - "
        f"column enforcement_state: '{value}' is not one of the four "
        "Enforcement states"
    ]


def test_a_bad_marking_is_refused_even_beside_a_detector(tmp_path: Path) -> None:
    result = _check(tmp_path, HEADER + "ZZ-04,checks/zz04.py,true\n")

    assert result.returncode == 1
    assert "refused:enforcement_state" in _findings(result.stdout)[0]


# ---------------------------------------------------------------------------
# Parsed, not split; a bad field costs that field only
# ---------------------------------------------------------------------------


def test_a_quoted_field_with_commas_does_not_shift_the_columns_after_it(
    tmp_path: Path,
) -> None:
    # Split on commas, the marking lands in the wrong column: the row would
    # read as carrying the state " quoted" and be refused.
    text = HEADER + '"ZZ-06","a, quoted, detector",enforced-but-non-blocking\n'

    read = registry.read_registry(_write(tmp_path, text))
    assert read.rows[0].values["detector"] == "a, quoted, detector"
    assert read.rows[0].values["enforcement_state"] == "enforced-but-non-blocking"

    result = _run("--registry", str(tmp_path / "registry.csv"))
    assert result.returncode == 0
    assert _findings(result.stdout) == []
    assert _exclusions(result.stdout) == []


def test_an_overflow_field_keeps_the_row_and_is_reported_once(
    tmp_path: Path,
) -> None:
    result = _check(tmp_path, HEADER + "ZZ-07,,unenforceable,stray\n")

    assert result.returncode == 0
    assert _findings(result.stdout) == []
    assert _exclusions(result.stdout) == [
        "exclusion: line 2: ZZ-07: column (overflow): "
        "row carries more fields than the header declares"
    ]
    assert "1 row(s)" in result.stdout
    assert "1 excluded field(s)" in result.stdout
    assert _dispositions(tmp_path, HEADER + "ZZ-07,,unenforceable,stray\n") == [
        "marked:unenforceable"
    ]


def test_an_overflow_field_does_not_hide_an_orphan(tmp_path: Path) -> None:
    result = _check(tmp_path, HEADER + "ZZ-07,,,stray\n")

    assert result.returncode == 1
    assert _findings(result.stdout)[0].startswith("finding: line 2: ZZ-07: orphan - ")
    assert len(_exclusions(result.stdout)) == 1


def test_a_short_row_is_refused_for_the_absent_column_and_is_not_an_orphan(
    tmp_path: Path,
) -> None:
    result = _check(tmp_path, HEADER + "ZZ-01,\n")

    assert result.returncode == 1
    assert _findings(result.stdout) == [
        "finding: line 2: ZZ-01: refused:enforcement_state - "
        "column enforcement_state: column absent from row"
    ]
    assert "orphan" not in result.stdout


def test_a_refusal_names_the_first_failing_column_in_reading_order(
    tmp_path: Path,
) -> None:
    assert _dispositions(tmp_path, HEADER + "ZZ-01\n ,,true\n,checks/x.py\n") == [
        "refused:detector",
        "refused:id",
        "refused:id",
    ]


def test_rows_sharing_an_id_are_each_refused_with_their_own_line_number(
    tmp_path: Path,
) -> None:
    result = _check(
        tmp_path,
        HEADER + "ZZ-01,checks/a.py,\nZZ-02,checks/b.py,\nZZ-01,,unenforceable\n",
    )

    assert result.returncode == 1
    assert _findings(result.stdout) == [
        "finding: line 2: (no usable id): refused:id - "
        "column id: id 'ZZ-01' is also declared on line(s) 4",
        "finding: line 4: (no usable id): refused:id - "
        "column id: id 'ZZ-01' is also declared on line(s) 2",
    ]


def test_a_row_with_an_empty_id_is_refused_and_named_by_line_number(
    tmp_path: Path,
) -> None:
    result = _check(tmp_path, HEADER + "ZZ-01,checks/a.py,\n  ,checks/b.py,\n")

    assert result.returncode == 1
    assert _findings(result.stdout) == [
        "finding: line 3: (no usable id): refused:id - column id: id is empty"
    ]


@pytest.mark.parametrize(
    ("char", "escaped"), [("\u2028", "\\u2028"), ("\x85", "\\x85")]
)
def test_an_id_holding_a_line_separator_cannot_forge_an_outcome_line(
    tmp_path: Path, char: str, escaped: str
) -> None:
    """The parser keeps these in the cell; printed raw, each would end a line."""
    result = _check(
        tmp_path, HEADER + f'"ZZ-01{char}clean:constraint-registry - 1",,\n'
    )

    assert result.returncode == 1
    lines = result.stdout.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith(
        f"finding: line 2: ZZ-01{escaped}clean:constraint-registry - 1: orphan - "
    )
    assert not any(line.startswith("clean:") for line in lines)


def _run_without_bytecode(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the check with ``-B``, so the run writes nothing into the tree."""
    return subprocess.run(
        [sys.executable, "-B", str(_CHECK), *args], capture_output=True, text=True
    )


#: Read leniently, lines 3 and 4 vanish into the cell opened on line 2: an
#: orphan and a row naming a missing Detector are hidden, and two rows are read.
_HIDDEN_ROWS = (
    "id,detector,enforcement_state,note\n"
    'ZZ-01,,not-yet-enforced,"zz note\n'
    "ZZ-02,zz_gone.py,enforced-and-blocking,\n"
    'ZZ-03,,,"\n'
    "ZZ-04,,unenforceable,\n"
)


@pytest.mark.parametrize(
    "text",
    [HEADER + '"ZZ-01\nclean:constraint-registry - 1",,\n', _HIDDEN_ROWS],
    ids=["an-id-over-two-lines", "rows-between-two-quotes"],
)
def test_a_registry_cell_holding_a_line_break_is_unchecked_and_exits_two(
    tmp_path: Path, text: str
) -> None:
    result = _run_without_bytecode("--registry", str(_write(tmp_path, text)))

    assert result.returncode == 2
    assert result.stdout.splitlines() == [result.stdout.rstrip("\n")]
    assert result.stdout.startswith("unchecked:constraint-registry - ")
    assert "holds a line break inside a cell" in result.stdout
    assert _findings(result.stdout) == []


def test_the_quotation_fixture_as_it_was_shipped_over_three_lines_is_refused(
    tmp_path: Path,
) -> None:
    """A quoted orphan row on a line of its own is no longer a readable registry."""
    text = (
        "id,detector,enforcement_state,note\n"
        'ZZ-01,checks/zz01.py,,"labelled evidentiary quotation - the row below '
        "is quoted as evidence of an orphan and is not a row of this registry:\n"
        "ZZ-09,,\n"
        '"\n'
        "ZZ-02,,not-yet-enforced,\n"
    )

    result = _run_without_bytecode("--registry", str(_write(tmp_path, text)))

    assert result.returncode == 2
    assert result.stdout.startswith("unchecked:constraint-registry - ")
    assert "ends on line 4;" in result.stdout
    assert _findings(result.stdout) == []


# ---------------------------------------------------------------------------
# Zero rows, and a registry that could not be checked
# ---------------------------------------------------------------------------


def test_header_only_reports_empty_and_never_the_no_finding_token(
    tmp_path: Path,
) -> None:
    result = _check(tmp_path, HEADER)

    assert result.returncode == 0
    assert result.stdout.startswith("empty:constraint-registry - ")
    assert len(result.stdout.splitlines()) == 1
    assert "clean:" not in result.stdout
    assert "unchecked:" not in result.stdout


def test_a_registry_path_that_does_not_exist_is_unchecked_and_exits_two(
    tmp_path: Path,
) -> None:
    missing = _run("--registry", str(tmp_path / "absent.csv"))
    empty = _check(tmp_path, HEADER)

    assert missing.returncode == 2
    assert missing.stdout.startswith("unchecked:constraint-registry - no file at ")
    assert "empty:" not in missing.stdout
    assert "clean:" not in missing.stdout
    assert missing.stdout != empty.stdout
    assert missing.returncode != empty.returncode


def test_a_missing_default_registry_is_unchecked_and_exits_two(
    tmp_path: Path,
) -> None:
    # The two modules alone, with no registry beside them.
    shutil.copy(_REGISTRY_MODULE, tmp_path)
    copied = Path(shutil.copy(_CHECK, tmp_path))

    result = _run(check=copied)

    assert result.returncode == 2
    assert result.stdout.startswith("unchecked:constraint-registry - no file at ")
    assert str(tmp_path / "constraint-registry.csv") in result.stdout


def test_the_default_registry_is_the_file_beside_the_check(tmp_path: Path) -> None:
    shutil.copy(_REGISTRY_MODULE, tmp_path)
    copied = Path(shutil.copy(_CHECK, tmp_path))
    (tmp_path / "constraint-registry.csv").write_text(
        HEADER + "ZZ-03,,\n", encoding="utf-8"
    )

    result = _run(check=copied)

    assert result.returncode == 1
    assert _findings(result.stdout)[0].startswith("finding: line 2: ZZ-03: orphan - ")


@pytest.mark.parametrize(
    ("header", "named"),
    [
        ("id,detector\n", "enforcement_state"),
        ("detector,enforcement_state\n", "id"),
    ],
)
def test_a_header_missing_a_required_column_is_unchecked_and_names_the_column(
    tmp_path: Path, header: str, named: str
) -> None:
    result = _check(tmp_path, header + "ZZ-03,,\n")

    assert result.returncode == 2
    assert result.stdout.startswith("unchecked:constraint-registry - ")
    assert result.stdout.rstrip().endswith(f"missing required column(s): {named}")
    assert _findings(result.stdout) == []


def test_a_header_declaring_a_required_column_twice_is_unchecked(
    tmp_path: Path,
) -> None:
    result = _check(tmp_path, "id,detector,detector,enforcement_state\nZZ-03,,,\n")

    assert result.returncode == 2
    assert result.stdout.startswith("unchecked:constraint-registry - ")
    assert result.stdout.rstrip().endswith("more than once: detector")


def test_a_zero_byte_registry_is_unchecked_and_exits_two(tmp_path: Path) -> None:
    result = _check(tmp_path, "")

    assert result.returncode == 2
    assert result.stdout.startswith("unchecked:constraint-registry - ")
    assert "no header row" in result.stdout
    assert "empty:" not in result.stdout


def test_an_unreadable_registry_is_unchecked_and_never_an_empty_read(
    tmp_path: Path,
) -> None:
    # A directory where the registry should be: unreadable for any user.
    path = tmp_path / "registry.csv"
    path.mkdir()

    result = _run("--registry", str(path))

    assert result.returncode == 2
    assert result.stdout.startswith("unchecked:constraint-registry - ")
    assert "could not be read" in result.stdout
    assert "empty:" not in result.stdout
    assert "clean:" not in result.stdout


def test_a_registry_that_cannot_be_parsed_is_unchecked_and_exits_two(
    tmp_path: Path,
) -> None:
    result = _check(tmp_path, HEADER + "ZZ-01," + "x" * 200_000 + ",\n")

    assert result.returncode == 2
    assert result.stdout.startswith("unchecked:constraint-registry - ")
    assert "could not be parsed" in result.stdout


@pytest.mark.parametrize(
    "text",
    [
        # The open quote sits in a column the header declares.
        "id,detector,enforcement_state,note\n"
        'ZZ-01,checks/a.py,,"see ticket\n'
        "ZZ-02,,\n"
        "ZZ-03,,true\n",
        # The open quote sits in a field beyond the header's width.
        HEADER + 'ZZ-01,checks/a.py,,"see ticket\nZZ-02,,\nZZ-03,,true\n',
    ],
    ids=["declared-column", "overflow-field"],
)
def test_a_quote_that_is_never_closed_is_unchecked_and_exits_two(
    tmp_path: Path, text: str
) -> None:
    # The rows after the open quote hold an orphan and a bare boolean. A
    # lenient parser folds them into one field and the run passes.
    result = _check(tmp_path, text)

    assert result.returncode == 2
    assert result.stdout.startswith("unchecked:constraint-registry - ")
    assert "could not be parsed" in result.stdout
    assert "clean:" not in result.stdout
    assert "empty:" not in result.stdout


def test_a_wrong_command_line_exits_two(tmp_path: Path) -> None:
    result = _run("--no-such-option")

    assert result.returncode == 2
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# The worked example, row for row
# ---------------------------------------------------------------------------


def test_worked_example_gives_each_row_its_documented_disposition(
    tmp_path: Path,
) -> None:
    assert _dispositions(tmp_path, WORKED_EXAMPLE) == [
        "bound",
        "marked:not-yet-enforced",
        "orphan",
        "refused:enforcement_state",
        "refused:enforcement_state",
        "bound",
        "marked:unenforceable",
        "orphan",
    ]


def test_worked_example_prints_four_findings_and_exits_one(tmp_path: Path) -> None:
    path = _write(tmp_path, WORKED_EXAMPLE)

    result = _run("--registry", str(path))

    scope = (
        "This check reads the rows of that one file only; it does not compare "
        "the registry against the constraint files on disk."
    )
    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        "finding: line 4: ZZ-03: orphan - "
        "no Detector and no Enforcement state is declared",
        "finding: line 5: ZZ-04: refused:enforcement_state - "
        "column enforcement_state: 'true' is not one of the four "
        "Enforcement states",
        "finding: line 6: ZZ-05: refused:enforcement_state - "
        "column enforcement_state: 'enforced-and-blocking' claims a working "
        "Detector and no Detector is declared",
        "finding: line 9: ZZ-08: orphan - "
        "no Detector and no Enforcement state is declared",
        "exclusion: line 5: ZZ-04: column enforcement_state: "
        "'true' is not one of the four Enforcement states",
        "exclusion: line 8: ZZ-07: column (overflow): "
        "row carries more fields than the header declares",
        f"checked 8 row(s) of {path}, 4 finding(s), 2 excluded field(s). {scope}",
    ]


# ---------------------------------------------------------------------------
# What the output must and must not say
# ---------------------------------------------------------------------------

_ALL_FIXTURES = {
    "worked-example": WORKED_EXAMPLE,
    "header-only": HEADER,
    "no-findings": HEADER + "ZZ-01,checks/zz01.py,\nZZ-02,,not-yet-enforced\n",
    "every-state": HEADER
    + "ZZ-01,,unenforceable\nZZ-02,,not-yet-enforced\n"
    + "ZZ-03,a.py,enforced-but-non-blocking\nZZ-04,b.py,enforced-and-blocking\n",
    "missing-column": "id,detector\nZZ-01,\n",
    "zero-byte": "",
}


@pytest.mark.parametrize("name", sorted(_ALL_FIXTURES))
def test_no_output_carries_a_combined_unenforced_figure(
    tmp_path: Path, name: str
) -> None:
    result = _check(tmp_path, _ALL_FIXTURES[name])

    # No fixture here uses the word as a value, so it may not appear at all;
    # and no state token may appear beside a count.
    assert "unenforced" not in result.stdout.lower()
    for state in registry.ENFORCEMENT_STATES:
        assert not re.search(rf"\d+\s+{state}|{state}\s*[:=]\s*\d+", result.stdout)


@pytest.mark.parametrize("name", ["worked-example", "no-findings", "header-only"])
def test_a_line_carrying_a_count_or_an_outcome_says_what_was_left_out(
    tmp_path: Path, name: str
) -> None:
    result = _check(tmp_path, _ALL_FIXTURES[name])

    assert result.stdout.splitlines()[-1].endswith(
        "it does not compare the registry against the constraint files on disk."
    )


@pytest.mark.parametrize("name", sorted(_ALL_FIXTURES))
def test_exit_one_if_and_only_if_a_finding_line_was_printed(
    tmp_path: Path, name: str
) -> None:
    result = _check(tmp_path, _ALL_FIXTURES[name])

    assert (result.returncode == 1) == bool(_findings(result.stdout))
    assert result.returncode in (0, 1, 2)
    assert result.stderr == ""


def test_the_exit_status_is_decided_from_the_findings_that_are_printed(
    tmp_path: Path,
) -> None:
    read = registry.read_registry(_write(tmp_path, WORKED_EXAMPLE))
    findings = orphan_check.find(read)

    assert orphan_check.exit_status(read, findings) == 1
    assert orphan_check.exit_status(read, []) == 0
    assert orphan_check.render(read, findings)[: len(findings)] == findings

    unchecked = registry.read_registry(tmp_path / "absent.csv")
    assert orphan_check.exit_status(unchecked, []) == 2


def test_a_row_disposition_is_available_without_running_the_command(
    tmp_path: Path,
) -> None:
    read = registry.read_registry(_write(tmp_path, HEADER + "ZZ-03,,\n"))

    disposition = orphan_check.row_disposition(read.rows[0])

    assert disposition.token == "orphan"
    assert disposition.is_finding is True


# ---------------------------------------------------------------------------
# The registry the product ships
# ---------------------------------------------------------------------------


@pytest.mark.process
def test_shipped_registry_declares_the_required_columns_and_passes_the_check() -> None:
    assert _SHIPPED_REGISTRY.is_file()
    with _SHIPPED_REGISTRY.open(encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle))
    assert set(registry.REQUIRED_COLUMNS) <= set(header)

    result = _run()

    assert result.returncode == 0
    assert _findings(result.stdout) == []
    assert "unchecked" not in result.stdout
    assert re.match(r"(empty|clean):constraint-registry - ", result.stdout)

"""Tests for the enforcement report.

The report counts the rows of one Constraint registry in the four
Enforcement states and prints the four counts separately. It is a report and
not a gate: it exits 0 whenever it was produced.

Every case except the shipped tree is built on ``tmp_path``: a registry as
CSV text and, where a row names a Detector, a directory of stub Detectors
and their fixture pairs written by the test. Identifiers are synthetic. No
stub is committed.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import itertools
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from memory.degraded import ENFORCEMENT_STATES, POV_TREE

# ---------------------------------------------------------------------------
# Module loading: in dependency order, each registered under the name its
# siblings import, before the next one is executed
# ---------------------------------------------------------------------------

_DETECTORS_DIR = Path(__file__).resolve().parent.parent / POV_TREE / "detectors"
_REPORT = _DETECTORS_DIR / "enforcement_report.py"
_BINDING_CHECK = _DETECTORS_DIR / "binding_check.py"
_SHIPPED_REGISTRY = _DETECTORS_DIR / "constraint-registry.csv"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _DETECTORS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


registry = _load("constraint_registry")
orphan_check = _load("orphan_check")
binding_check = _load("binding_check")
enforcement_report = _load("enforcement_report")

UNENFORCEABLE, NOT_YET, NON_BLOCKING, BLOCKING = ENFORCEMENT_STATES

HEADER = "id,detector,enforcement_state\n"

FLAG = "ZZ-FLAG"

#: Exits 1 when the file it is given holds FLAG, else 0.
STUB = f"""import sys

if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as handle:
        sys.exit(1 if "{FLAG}" in handle.read() else 0)
"""


def _always(code: int) -> str:
    return f'import sys\n\nif __name__ == "__main__":\n    sys.exit({code})\n'


def _detector(root: Path, name: str, source: str = STUB, pair: bool = True) -> None:
    """Write the stub Detector *name* in *root*, with a pair unless told not to."""
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.py").write_text(source, encoding="utf-8")
    if not pair:
        return
    fixtures = root / "fixtures" / name
    fixtures.mkdir(parents=True)
    (fixtures / "positive.txt").write_text(f"{FLAG}\n", encoding="utf-8")
    (fixtures / "negative.txt").write_text("zz-quiet\n", encoding="utf-8")
    manifest = {
        "fixture_marker": "synthetic-fixture",
        "args": ["{fixture}"],
        "positive": "positive.txt",
        "negative": "negative.txt",
        "exemptions": {},
    }
    (fixtures / "fixture-pair.json").write_text(json.dumps(manifest), encoding="utf-8")


def _registry(tmp_path: Path, rows: str) -> Path:
    path = tmp_path / "registry.csv"
    path.write_text(HEADER + rows, encoding="utf-8", newline="")
    return path


def _run(*args: str, env: dict[str, str] | None = None):
    return subprocess.run(
        [sys.executable, "-B", str(_REPORT), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _report(reg: Path, detectors: Path):
    """Run the report both ways and hold them to one answer."""
    result = _run("--registry", str(reg), "--detectors", str(detectors))
    built = enforcement_report.build_report(reg, detectors)
    assert result.stdout.splitlines() == enforcement_report.render(built)
    assert result.returncode == enforcement_report.exit_status(built)
    return result, built


def _state_lines(out: str) -> list[tuple[str, str]]:
    """The printed state lines, in the order printed, as (token, count)."""
    return re.findall(
        r"^(" + "|".join(map(re.escape, ENFORCEMENT_STATES)) + r"): (\S+)$", out, re.M
    )


def _counts(out: str) -> dict[str, int]:
    lines = _state_lines(out)
    assert [token for token, _ in lines] == list(ENFORCEMENT_STATES)
    return {token: int(count) for token, count in lines}


def _line(out: str, token: str) -> str | None:
    """The one line that starts with *token*, or None when there is none."""
    found = [line for line in out.splitlines() if line.startswith(f"{token}: ")]
    assert len(found) <= 1
    return found[0] if found else None


def _by_id(built) -> dict[str, tuple[str | None, str, str]]:
    return {row.id: (row.state, row.counted_line, row.reason) for row in built.rows}


# ---------------------------------------------------------------------------
# The report's own pair: T1 must flag, T2 must not
# ---------------------------------------------------------------------------


def test_fixture_pair_a_row_in_no_state_is_counted_on_its_own_line(
    tmp_path: Path,
) -> None:
    """T1, the report's pair, must-flag: an orphan row is said, not left out."""
    reg = _registry(tmp_path, "ZZ-01,,\n")

    result, built = _report(reg, tmp_path / "zz-not-read")

    assert result.returncode == 0
    assert _counts(result.stdout) == dict.fromkeys(ENFORCEMENT_STATES, 0)
    line = _line(result.stdout, "uncounted")
    assert line is not None
    assert line.startswith("uncounted: 1 row(s) ")
    assert line.endswith(" - line 2 [orphan]")
    assert "1 Constraint row(s) read" in _line(result.stdout, "rows")
    assert "1 of them in none of the four states" in _line(result.stdout, "rows")
    assert built.counted_lines["uncounted"] == 1
    assert _by_id(built) == {"ZZ-01": (None, "uncounted", "")}


def test_fixture_pair_a_marked_row_is_counted_in_its_state_and_nowhere_else(
    tmp_path: Path,
) -> None:
    """T2, the report's pair, must-not-flag: the same row, given a state."""
    reg = _registry(tmp_path, f"ZZ-01,,{NOT_YET}\n")

    result, built = _report(reg, tmp_path / "zz-not-read")

    assert result.returncode == 0
    assert _line(result.stdout, "uncounted") is None
    assert _counts(result.stdout) == {
        UNENFORCEABLE: 0,
        NOT_YET: 1,
        NON_BLOCKING: 0,
        BLOCKING: 0,
    }
    assert "0 of them in none of the four states" in _line(result.stdout, "rows")
    assert "clean" not in result.stdout
    assert "empty" not in result.stdout
    assert built.status == "reported"
    assert sum(built.counted_lines.values()) == 0


# ---------------------------------------------------------------------------
# AC-1: four states, separately, always the same four in the same order
# ---------------------------------------------------------------------------


def test_one_row_in_each_state_prints_four_lines_of_one_in_order(
    tmp_path: Path,
) -> None:
    """T3."""
    detectors = tmp_path / "detectors"
    _detector(detectors, "zz_ok")
    reg = _registry(
        tmp_path,
        f"ZZ-01,,{UNENFORCEABLE}\n"
        f"ZZ-02,,{NOT_YET}\n"
        f"ZZ-03,zz_ok.py,{NON_BLOCKING}\n"
        f"ZZ-04,zz_ok.py,{BLOCKING}\n",
    )

    result, _ = _report(reg, detectors)

    assert _state_lines(result.stdout) == [(state, "1") for state in ENFORCEMENT_STATES]
    assert result.stdout.splitlines()[:4] == [f"{s}: 1" for s in ENFORCEMENT_STATES]


def test_a_state_with_no_rows_prints_zero_and_is_not_left_out(tmp_path: Path) -> None:
    """T3, second half."""
    reg = _registry(tmp_path, f"ZZ-01,,{UNENFORCEABLE}\n")

    result, _ = _report(reg, tmp_path / "zz-not-read")

    assert _state_lines(result.stdout) == [
        (UNENFORCEABLE, "1"),
        (NOT_YET, "0"),
        (NON_BLOCKING, "0"),
        (BLOCKING, "0"),
    ]


def test_the_printed_state_tokens_are_the_declared_ones_in_order(
    tmp_path: Path,
) -> None:
    """T11: the surface an operator reads, held to ``memory.degraded``."""
    reg = _registry(tmp_path, f"ZZ-01,,{NOT_YET}\n")

    result, built = _report(reg, tmp_path / "zz-not-read")

    printed = [line.split(": ")[0] for line in result.stdout.splitlines()[:4]]
    assert tuple(printed) == ENFORCEMENT_STATES
    assert tuple(built.counts) == ENFORCEMENT_STATES


# ---------------------------------------------------------------------------
# AC-2: a Detector that does not refuse is not counted as one that does
# ---------------------------------------------------------------------------


def test_a_declared_non_blocking_row_is_never_counted_as_blocking(
    tmp_path: Path,
) -> None:
    """T4."""
    detectors = tmp_path / "detectors"
    _detector(detectors, "zz_ok")
    reg = _registry(tmp_path, f"ZZ-01,zz_ok.py,{NON_BLOCKING}\n")

    result, built = _report(reg, detectors)

    assert _counts(result.stdout) == {
        UNENFORCEABLE: 0,
        NOT_YET: 0,
        NON_BLOCKING: 1,
        BLOCKING: 0,
    }
    assert _by_id(built) == {"ZZ-01": (NON_BLOCKING, "", "")}
    assert result.stdout.splitlines()[4:] == [_line(result.stdout, "rows")]


def test_a_detector_that_cannot_fail_counts_in_neither_enforced_state(
    tmp_path: Path,
) -> None:
    """T5: the binding check's verdict is read, whatever the row declares."""
    detectors = tmp_path / "detectors"
    _detector(detectors, "zz_mute", _always(0))
    reg = _registry(
        tmp_path, f"ZZ-01,zz_mute.py,{BLOCKING}\nZZ-02,zz_mute.py,{NON_BLOCKING}\n"
    )

    result, built = _report(reg, detectors)

    assert result.returncode == 0
    assert _counts(result.stdout) == {
        UNENFORCEABLE: 0,
        NOT_YET: 2,
        NON_BLOCKING: 0,
        BLOCKING: 0,
    }
    line = _line(result.stdout, "lowered")
    assert line.startswith("lowered: 2 row(s) ")
    assert line.endswith(" - line 2 [non-functional], line 3 [non-functional]")
    assert _by_id(built) == {
        "ZZ-01": (NOT_YET, "lowered", "non-functional"),
        "ZZ-02": (NOT_YET, "lowered", "non-functional"),
    }


# ---------------------------------------------------------------------------
# AC-4: every fail-open condition is a counted line
# ---------------------------------------------------------------------------


def test_a_row_whose_detector_is_not_shown_to_work_is_lowered_with_its_reason(
    tmp_path: Path,
) -> None:
    """T6."""
    detectors = tmp_path / "detectors"
    _detector(detectors, "zz_ok")
    _detector(detectors, "zz_nopair", pair=False)
    _detector(detectors, "zz_two", _always(2))
    (detectors / "zz_sub").mkdir()
    (detectors / "zz_sub" / "zz_ok.py").write_text(STUB, encoding="utf-8")
    reg = _registry(
        tmp_path,
        f"ZZ-01,zz_nopair.py,{BLOCKING}\n"
        f"ZZ-02,zz_absent.py,{BLOCKING}\n"
        f"ZZ-03,zz_sub/zz_ok.py,{BLOCKING}\n"
        f"ZZ-04,binding_check.py,{BLOCKING}\n"
        f"ZZ-05,zz_two.py,{BLOCKING}\n"
        f"ZZ-06,zz_ok,{BLOCKING}\n"
        f"ZZ-07,{detectors}/zz_ok.py,{BLOCKING}\n"
        f"ZZ-08,ZZ_OK.PY,{BLOCKING}\n",
    )

    result, built = _report(reg, detectors)

    assert result.returncode == 0
    assert _by_id(built) == {
        "ZZ-01": (NOT_YET, "lowered", "unbound"),
        "ZZ-02": (NOT_YET, "lowered", "not-found"),
        "ZZ-03": (NOT_YET, "lowered", "not-found"),
        "ZZ-04": (NOT_YET, "lowered", "not-found"),
        "ZZ-05": (NOT_YET, "lowered", "unchecked:zz_two"),
        "ZZ-06": (NOT_YET, "lowered", "not-found"),
        "ZZ-07": (NOT_YET, "lowered", "not-found"),
        "ZZ-08": (NOT_YET, "lowered", "not-found"),
    }
    assert _counts(result.stdout)[NOT_YET] == 8
    assert _counts(result.stdout)[BLOCKING] == 0
    line = _line(result.stdout, "lowered")
    assert line.startswith("lowered: 8 row(s) ")
    assert line.endswith(
        " - line 2 [unbound], line 3 [not-found], line 4 [not-found], "
        "line 5 [not-found], line 6 [unchecked:zz_two], line 7 [not-found], "
        "line 8 [not-found], line 9 [not-found]"
    )


def test_a_row_naming_a_program_the_binding_check_skips_names_no_detector(
    tmp_path: Path,
) -> None:
    """T6: in the shipped directory, neither skipped file has a verdict."""
    reg = _registry(
        tmp_path,
        f"ZZ-01,binding_check.py,{BLOCKING}\n"
        f"ZZ-02,enforcement_report.py,{BLOCKING}\n",
    )

    built = enforcement_report.build_report(reg, _DETECTORS_DIR)

    assert _by_id(built) == {
        "ZZ-01": (NOT_YET, "lowered", "not-found"),
        "ZZ-02": (NOT_YET, "lowered", "not-found"),
    }


def test_a_working_detector_and_no_declared_state_is_the_lower_enforced_state(
    tmp_path: Path,
) -> None:
    """T7."""
    detectors = tmp_path / "detectors"
    _detector(detectors, "zz_ok")
    reg = _registry(tmp_path, f"ZZ-01,zz_ok.py,\nZZ-02,zz_ok.py,{NOT_YET}\n")

    result, built = _report(reg, detectors)

    assert _counts(result.stdout) == {
        UNENFORCEABLE: 0,
        NOT_YET: 1,
        NON_BLOCKING: 1,
        BLOCKING: 0,
    }
    line = _line(result.stdout, "undeclared-state")
    assert line.startswith("undeclared-state: 1 row(s) ")
    assert line.endswith(" - line 2")
    assert _line(result.stdout, "lowered") is None
    assert _by_id(built) == {
        "ZZ-01": (NON_BLOCKING, "undeclared-state", ""),
        "ZZ-02": (NOT_YET, "", ""),
    }


@pytest.mark.parametrize("declared", [UNENFORCEABLE, NOT_YET])
def test_a_verdict_never_raises_and_a_lower_declared_state_is_not_lowered(
    tmp_path: Path, declared: str
) -> None:
    """A row that declares a lower state is counted as declared, either way."""
    detectors = tmp_path / "detectors"
    _detector(detectors, "zz_ok")
    reg = _registry(
        tmp_path, f"ZZ-01,zz_ok.py,{declared}\nZZ-02,zz_absent.py,{declared}\n"
    )

    result, built = _report(reg, detectors)

    assert _by_id(built) == {"ZZ-01": (declared, "", ""), "ZZ-02": (declared, "", "")}
    assert _counts(result.stdout)[declared] == 2
    assert _line(result.stdout, "lowered") is None


def test_a_dropped_field_is_counted_and_its_row_is_still_counted(
    tmp_path: Path,
) -> None:
    """T8, first half: an overflow field."""
    reg = _registry(tmp_path, f"ZZ-01,,{UNENFORCEABLE},zz-stray\n")

    result, built = _report(reg, tmp_path / "zz-not-read")

    assert result.returncode == 0
    assert _counts(result.stdout)[UNENFORCEABLE] == 1
    line = _line(result.stdout, "field-exclusion")
    assert line.startswith("field-exclusion: 1 field(s) ")
    assert line.endswith(" - line 2 [(overflow)]")
    assert _line(result.stdout, "uncounted") is None
    assert built.counted_lines["field-exclusion"] == 1


def test_field_exclusions_are_counted_in_fields_and_uncounted_rows_in_rows(
    tmp_path: Path,
) -> None:
    """T8, second half: two rows sharing an id, and a row with two bad fields."""
    reg = _registry(
        tmp_path,
        f"ZZ-01,,{UNENFORCEABLE}\nZZ-01,,{NOT_YET}\nZZ-03,,zz-not-a-state,zz-stray\n",
    )

    result, built = _report(reg, tmp_path / "zz-not-read")

    assert result.returncode == 0
    assert _counts(result.stdout) == dict.fromkeys(ENFORCEMENT_STATES, 0)
    fields = _line(result.stdout, "field-exclusion")
    assert fields.startswith("field-exclusion: 4 field(s) ")
    assert "fields" in fields
    assert fields.endswith(
        " - line 2 [id], line 3 [id], line 4 [enforcement_state], line 4 [(overflow)]"
    )
    rows = _line(result.stdout, "uncounted")
    assert rows.startswith("uncounted: 3 row(s) ")
    assert rows.endswith(
        " - line 2 [refused:id], line 3 [refused:id], "
        "line 4 [refused:enforcement_state]"
    )
    assert built.counted_lines["field-exclusion"] == 4
    assert built.counted_lines["uncounted"] == 3


def test_a_disposition_the_table_does_not_name_is_counted_in_no_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T20: never guessed into a state."""
    reg = _registry(tmp_path, f"ZZ-01,,{NOT_YET}\nZZ-02,,{UNENFORCEABLE}\n")
    monkeypatch.setattr(
        orphan_check,
        "row_disposition",
        lambda row: orphan_check.Disposition(f"marked:{BLOCKING}", False),
    )

    built = enforcement_report.build_report(reg, tmp_path / "zz-not-read")

    assert dict(built.counts) == dict.fromkeys(ENFORCEMENT_STATES, 0)
    assert _by_id(built) == {
        "ZZ-01": (None, "uncounted", ""),
        "ZZ-02": (None, "uncounted", ""),
    }
    line = enforcement_report.render(built)[5]
    assert line.startswith("uncounted: 2 row(s) ")
    assert line.endswith(f" - line 2 [marked:{BLOCKING}], line 3 [marked:{BLOCKING}]")


# ---------------------------------------------------------------------------
# AC-3: no collapsed figure
# ---------------------------------------------------------------------------


def test_no_sum_of_two_or_three_states_is_printed_and_there_is_no_percentage(
    tmp_path: Path,
) -> None:
    """T9: 1, 2, 4 and 8 rows, so every partial sum is a number of its own."""
    detectors = tmp_path / "detectors"
    _detector(detectors, "zz_ok")
    amounts = dict(zip(ENFORCEMENT_STATES, (1, 2, 4, 8), strict=True))
    detector = {NON_BLOCKING: "zz_ok.py", BLOCKING: "zz_ok.py"}
    rows = "".join(
        f"ZZ-{state}-{n},{detector.get(state, '')},{state}\n"
        for state, amount in amounts.items()
        for n in range(amount)
    )
    reg = _registry(tmp_path, rows)

    result, built = _report(reg, detectors)

    assert _counts(result.stdout) == amounts
    # The path holds digits of its own; everything else printed is the report's.
    text = result.stdout.replace(str(reg), "<registry>")
    numbers = {int(n) for n in re.findall(r"\d+", text)}
    partial_sums = {
        sum(group)
        for size in (2, 3)
        for group in itertools.combinations(amounts.values(), size)
    }
    assert numbers == {0, 1, 2, 4, 8, 15}
    assert not numbers & partial_sums
    assert "%" not in result.stdout
    assert "percent" not in result.stdout.lower()
    assert set(built.counts.values()) == {1, 2, 4, 8}


def test_the_typed_result_holds_no_combined_figure() -> None:
    """T9: the result's whole public surface, and nothing computed on it."""

    def public(cls: type) -> set[str]:
        return {name for name in dir(cls) if not name.startswith("_")}

    report = enforcement_report.EnforcementReport
    row = enforcement_report.ReportRow

    assert {f.name for f in dataclasses.fields(report)} == {
        "status",
        "counts",
        "rows",
        "counted_lines",
        "detail",
    }
    assert {f.name for f in dataclasses.fields(row)} == {
        "line",
        "id",
        "disposition",
        "state",
        "counted_line",
        "reason",
        "excluded",
    }
    # A dataclass field with no default is not a class attribute, so anything
    # public on the class is a property or a method.
    assert public(report) == set()
    assert public(row) == set()
    assert report.__dataclass_params__.frozen
    assert row.__dataclass_params__.frozen


# ---------------------------------------------------------------------------
# Outcomes and the exit status
# ---------------------------------------------------------------------------


def test_a_registry_with_no_rows_is_empty_with_four_zeros_and_never_clean(
    tmp_path: Path,
) -> None:
    """T13, first half."""
    reg = _registry(tmp_path, "")

    result, built = _report(reg, tmp_path / "zz-not-read")

    assert result.returncode == 0
    assert _counts(result.stdout) == dict.fromkeys(ENFORCEMENT_STATES, 0)
    lines = result.stdout.splitlines()
    assert len(lines) == 5
    assert lines[4].startswith("empty:enforcement-report - 0 Constraint rows ")
    assert "clean" not in result.stdout
    assert _line(result.stdout, "rows") is None
    assert built.status == "empty"


@pytest.mark.parametrize(
    "text",
    [
        None,
        "id,detector\nZZ-01,\n",
        'id,detector,enforcement_state\nZZ-01,"zz-open,\nZZ-02,,\n',
    ],
    ids=["no-file", "header-lacks-a-column", "quote-never-closed"],
)
def test_a_registry_that_cannot_be_checked_is_unchecked_with_no_state_line(
    tmp_path: Path, text: str | None
) -> None:
    """T13, second half: never four zeros for a file that was not read."""
    reg = tmp_path / "registry.csv"
    if text is not None:
        reg.write_text(text, encoding="utf-8")

    result, built = _report(reg, tmp_path / "zz-not-read")

    assert result.returncode == 2
    lines = result.stdout.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("unchecked:enforcement-report - ")
    assert _state_lines(result.stdout) == []
    assert built.status == "unchecked"
    assert built.rows == ()
    assert dict(built.counts) == dict.fromkeys(ENFORCEMENT_STATES, 0)


@pytest.mark.parametrize("kind", ["absent", "a-file"])
def test_a_bound_row_and_no_readable_detectors_directory_is_unchecked(
    tmp_path: Path, kind: str
) -> None:
    """T14: a count is never produced from Detector evidence that was not read."""
    detectors = tmp_path / "zz-detectors"
    if kind == "a-file":
        detectors.write_text("zz", encoding="utf-8")
    bound = f"ZZ-01,zz_ok.py,{BLOCKING}\n"
    marked = f"ZZ-02,,{NOT_YET}\n"

    result, built = _report(_registry(tmp_path, bound + marked), detectors)

    assert result.returncode == 2
    assert result.stdout.splitlines()[0].startswith("unchecked:enforcement-report - ")
    assert len(result.stdout.splitlines()) == 1
    assert _state_lines(result.stdout) == []
    assert built.rows == ()

    result, built = _report(_registry(tmp_path, marked), detectors)

    assert result.returncode == 0
    assert _counts(result.stdout)[NOT_YET] == 1
    assert "unchecked" not in result.stdout


def test_the_detectors_directory_is_not_read_when_no_row_names_a_detector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T14: no bound row, no Detector evidence asked for."""
    calls = []
    monkeypatch.setattr(
        binding_check, "check_bindings", lambda root: calls.append(root)
    )

    enforcement_report.build_report(
        _registry(tmp_path, f"ZZ-01,,{NOT_YET}\nZZ-02,,\n"), tmp_path
    )

    assert calls == []


def test_the_exit_status_is_zero_or_two_and_decided_in_one_place(
    tmp_path: Path,
) -> None:
    """A row in no state does not make the report exit non-zero; it is no gate."""
    reg = _registry(tmp_path, "ZZ-01,,\nZZ-02,,zz-not-a-state\nZZ-03,zz_absent.py,\n")
    (tmp_path / "detectors").mkdir()

    result, built = _report(reg, tmp_path / "detectors")

    assert result.returncode == 0
    assert built.counted_lines["uncounted"] == 2
    assert enforcement_report.exit_status(built) == 0
    unchecked = dataclasses.replace(built, status="unchecked")
    assert enforcement_report.exit_status(unchecked) == 2


def test_a_wrong_command_line_exits_two(tmp_path: Path) -> None:
    result = _run("--zz-no-such-option")

    assert result.returncode == 2
    assert result.stdout == ""


def test_a_failure_inside_the_report_exits_two_and_never_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An uncaught exception would exit 1, which this report never returns."""

    def broken(*_args: object) -> None:
        raise RuntimeError("zz-report-crash")

    monkeypatch.setattr(enforcement_report, "build_report", broken)

    status = enforcement_report.main(["--registry", str(tmp_path / "registry.csv")])

    out = capsys.readouterr().out
    assert status == 2
    assert out.startswith("unchecked:enforcement-report - the report itself failed: ")
    assert _state_lines(out) == []


def test_the_exit_status_does_not_depend_on_what_reached_the_screen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed write must not turn exit 2 into exit 0, nor a report into one."""
    absent = ["--registry", str(tmp_path / "zz-absent.csv")]
    present = ["--registry", str(_registry(tmp_path, f"ZZ-01,,{NOT_YET}\n"))]

    monkeypatch.setattr("builtins.print", lambda *a, **k: None)
    assert enforcement_report.main(absent) == 2
    assert enforcement_report.main(present) == 0

    def broken(*args: object, **kwargs: object) -> None:
        raise OSError("zz-closed")

    monkeypatch.setattr("builtins.print", broken)
    assert enforcement_report.main(absent) == 2
    assert enforcement_report.main(present) == 2


# ---------------------------------------------------------------------------
# What a file can put into a printed line
# ---------------------------------------------------------------------------


def test_a_name_read_from_a_file_cannot_forge_a_line_or_a_counted_item(
    tmp_path: Path,
) -> None:
    """A fixture id and a registry path are printed; neither can add a line."""
    detectors = tmp_path / "detectors"
    forged = f"zz], line 99 [functional\n{BLOCKING}: 7"
    _detector(detectors, "zz_fp")
    pair = detectors / "fixtures" / "zz_fp"
    (pair / "zz-exempt.txt").write_text(f"{FLAG}\n", encoding="utf-8")
    manifest = json.loads((pair / "fixture-pair.json").read_text(encoding="utf-8"))
    manifest["exemptions"] = {forged: "zz-exempt.txt"}
    (pair / "fixture-pair.json").write_text(json.dumps(manifest), encoding="utf-8")
    folder = tmp_path / f"zz\n{BLOCKING}: 9"
    folder.mkdir()
    reg = _registry(folder, f"ZZ-01,zz_fp.py,{BLOCKING}\n")

    result, built = _report(reg, detectors)

    assert built.rows[0].reason == f"false-positive:{forged}"
    assert _counts(result.stdout)[BLOCKING] == 0
    assert len(result.stdout.splitlines()) == 6
    line = _line(result.stdout, "lowered")
    assert line.count("line ") == 1
    assert line.count("[") == 1
    assert line.count("]") == 1


def test_a_quoted_id_holding_a_line_break_does_not_hide_or_add_a_row(
    tmp_path: Path,
) -> None:
    """A quoted field may span lines; each record is still one row."""
    reg = _registry(tmp_path, f'"ZZ-01\n{BLOCKING}: 5",,\nZZ-02,,{NOT_YET}\n')

    result, built = _report(reg, tmp_path / "zz-not-read")

    assert len(built.rows) == 2
    assert _counts(result.stdout) == {
        UNENFORCEABLE: 0,
        NOT_YET: 1,
        NON_BLOCKING: 0,
        BLOCKING: 0,
    }
    assert _line(result.stdout, "uncounted").endswith(" - line 3 [orphan]")
    assert "2 Constraint row(s) read" in _line(result.stdout, "rows")


# ---------------------------------------------------------------------------
# The worked example
# ---------------------------------------------------------------------------


def test_the_worked_example_row_for_row_and_count_for_count(tmp_path: Path) -> None:
    """T18."""
    detectors = tmp_path / "detectors"
    _detector(detectors, "zz_ok")
    _detector(detectors, "zz_mute", _always(0))
    _detector(detectors, "zz_nopair", pair=False)
    reg = _registry(
        tmp_path,
        "ZZ-01,,unenforceable\n"
        "ZZ-02,,not-yet-enforced\n"
        "ZZ-03,zz_ok.py,enforced-and-blocking\n"
        "ZZ-04,zz_ok.py,enforced-but-non-blocking\n"
        "ZZ-05,zz_ok.py,\n"
        "ZZ-06,zz_mute.py,enforced-and-blocking\n"
        "ZZ-07,zz_nopair.py,enforced-but-non-blocking\n"
        "ZZ-08,zz_absent.py,enforced-and-blocking\n"
        "ZZ-09,zz_ok.py,not-yet-enforced\n"
        "ZZ-10,,\n",
    )

    result, built = _report(reg, detectors)

    assert result.returncode == 0
    assert _by_id(built) == {
        "ZZ-01": (UNENFORCEABLE, "", ""),
        "ZZ-02": (NOT_YET, "", ""),
        "ZZ-03": (BLOCKING, "", ""),
        "ZZ-04": (NON_BLOCKING, "", ""),
        "ZZ-05": (NON_BLOCKING, "undeclared-state", ""),
        "ZZ-06": (NOT_YET, "lowered", "non-functional"),
        "ZZ-07": (NOT_YET, "lowered", "unbound"),
        "ZZ-08": (NOT_YET, "lowered", "not-found"),
        "ZZ-09": (NOT_YET, "", ""),
        "ZZ-10": (None, "uncounted", ""),
    }
    assert [row.line for row in built.rows] == list(range(2, 12))
    assert built.rows[-1].disposition == "orphan"
    assert dict(built.counts) == {
        UNENFORCEABLE: 1,
        NOT_YET: 5,
        NON_BLOCKING: 2,
        BLOCKING: 1,
    }
    assert dict(built.counted_lines) == {
        "uncounted": 1,
        "lowered": 3,
        "undeclared-state": 1,
        "field-exclusion": 0,
    }
    scope = enforcement_report._SCOPE
    assert result.stdout.splitlines() == [
        "unenforceable: 1",
        "not-yet-enforced: 5",
        "enforced-but-non-blocking: 2",
        "enforced-and-blocking: 1",
        f"rows: 10 Constraint row(s) read from {reg}, 1 of them in none of the "
        f"four states. {scope}",
        "uncounted: 1 row(s) in none of the four states, each with its "
        "disposition from the orphan check - line 11 [orphan]",
        "lowered: 3 row(s) counted as not-yet-enforced because the Detector the "
        "row names is not shown to work, each with the reason - "
        "line 7 [non-functional], line 8 [unbound], line 9 [not-found]",
        "undeclared-state: 1 row(s) with a working Detector and no declared "
        "state, counted as enforced-but-non-blocking - line 6",
    ]
    for unsaid in ("Detector files", "capability declarations", "constraint files"):
        assert unsaid in scope


# ---------------------------------------------------------------------------
# The shipped tree
# ---------------------------------------------------------------------------


def _bytecode() -> set[Path]:
    return set(_DETECTORS_DIR.rglob("__pycache__"))


@pytest.mark.process
def test_the_shipped_report_runs_and_says_why_its_counts_are_zero() -> None:
    """T16: the report, with no arguments, against the shipped tree."""
    before = _bytecode()
    # Without this variable in the way, only -B keeps bytecode out of the tree.
    env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}

    result = _run(env=env)
    read = registry.read_registry(_SHIPPED_REGISTRY)

    assert result.returncode == 0
    assert result.stderr == ""
    assert "unchecked" not in result.stdout
    assert read.status != registry.UNCHECKED
    if not read.rows:
        assert _counts(result.stdout) == dict.fromkeys(ENFORCEMENT_STATES, 0)
        assert result.stdout.splitlines()[4].startswith("empty:enforcement-report - ")
        assert len(result.stdout.splitlines()) == 5
    else:
        assert sum(_counts(result.stdout).values()) <= len(read.rows)
    assert _bytecode() <= before, "the run wrote bytecode into the product tree"


def test_the_report_keeps_bytecode_out_only_because_it_is_run_with_b(
    tmp_path: Path,
) -> None:
    """The control for the bytecode assertion above, on a copy of the tree."""
    copy = tmp_path / "detectors"
    copy.mkdir()
    for path in _DETECTORS_DIR.glob("*.*"):
        (copy / path.name).write_bytes(path.read_bytes())
    env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}

    subprocess.run(
        [sys.executable, str(copy / _REPORT.name)],
        env=env,
        check=True,
        capture_output=True,
    )

    assert (copy / "__pycache__").is_dir()


@pytest.mark.process
def test_the_binding_check_skips_the_report_as_it_skips_itself() -> None:
    """T15, first half: against the shipped tree, with no arguments."""
    result = subprocess.run(
        [sys.executable, "-B", str(_BINDING_CHECK)], capture_output=True, text=True
    )

    assert (_BINDING_CHECK.name, _REPORT.name) == binding_check.SKIPPED_FILES
    assert result.returncode == 0
    reported = [
        line
        for line in result.stdout.splitlines()
        if line.startswith(("finding:", "detector:"))
    ]
    assert reported == ["detector: orphan_check.py: functional"]
    last = result.stdout.splitlines()[-1]
    assert f"{_BINDING_CHECK.name} and {_REPORT.name} were not checked" in last
    assert _REPORT.name not in binding_check.detector_files(_DETECTORS_DIR)


def test_the_second_skip_is_by_path_and_not_by_name(tmp_path: Path) -> None:
    """T15, second half: the same file name elsewhere is an ordinary file."""
    (tmp_path / _REPORT.name).write_text(_always(0), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-B", str(_BINDING_CHECK), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert f"finding: {_REPORT.name}: unbound - " in result.stdout
    assert binding_check.detector_files(tmp_path) == (_REPORT.name,)

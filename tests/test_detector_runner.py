"""Tests for the detector runner.

The runner reads the rows of one Constraint registry and reports every row
whose ``detector`` value names no Detector in one detectors directory. It
runs no Detector.

Every case except the shipped tree is built on ``tmp_path``: a registry as
CSV text and a directory of stub Detectors written by the test. Identifiers
are synthetic. No stub is committed.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from memory.degraded import POV_TREE

# ---------------------------------------------------------------------------
# Module loading: in dependency order, each registered under the name its
# siblings import, before the next one is executed
# ---------------------------------------------------------------------------

_DETECTORS_DIR = Path(__file__).resolve().parent.parent / POV_TREE / "detectors"
_RUNNER = _DETECTORS_DIR / "detector_runner.py"
_BINDING_CHECK = _DETECTORS_DIR / "binding_check.py"
_REPORT = _DETECTORS_DIR / "enforcement_report.py"
_MODULES = ("constraint_registry", "binding_check", "detector_runner")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _DETECTORS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


registry, binding_check, detector_runner = (_load(name) for name in _MODULES)

HEADER = "id,detector,enforcement_state\n"

#: A stub Detector: a program with a top-level ``__main__`` block.
STUB = 'import sys\n\nif __name__ == "__main__":\n    sys.exit(0)\n'

#: A module with no command line, so not a Detector.
LIBRARY = "VALUE = 1\n"

SUBJECT = "detector-resolution"

WORKED_EXAMPLE = (
    HEADER + "ZZ-01,zz_ok.py,enforced-and-blocking\n"
    "ZZ-02,zz_gone.py,enforced-and-blocking\n"
    "ZZ-03,zz_ok,enforced-but-non-blocking\n"
    "ZZ-04,sub/zz_deep.py,\n"
    "ZZ-05,zz_lib.py,\n"
    "ZZ-06,,not-yet-enforced\n"
)


def _detectors(tmp_path: Path) -> Path:
    """A detectors directory: one Detector, one module, one Detector in a sub-directory."""
    root = tmp_path / "detectors"
    (root / "sub").mkdir(parents=True)
    (root / "zz_ok.py").write_text(STUB, encoding="utf-8")
    (root / "zz_lib.py").write_text(LIBRARY, encoding="utf-8")
    (root / "sub" / "zz_deep.py").write_text(STUB, encoding="utf-8")
    return root


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "registry.csv"
    path.write_text(text, encoding="utf-8")
    return path


def _run(
    *args: str, runner: Path = _RUNNER, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(runner), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _resolve(tmp_path: Path, text: str) -> subprocess.CompletedProcess[str]:
    """Run the runner on *text* against the stub detectors directory."""
    root = tmp_path / "detectors"
    if not root.exists():
        _detectors(tmp_path)
    return _run("--registry", str(_write(tmp_path, text)), "--detectors", str(root))


def _findings(out: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith("finding:")]


def _last(out: str) -> str:
    return out.splitlines()[-1]


def _tokens(tmp_path: Path, text: str) -> dict[int, str]:
    root = tmp_path / "detectors"
    if not root.exists():
        _detectors(tmp_path)
    result = detector_runner.enumerate_constraints(_write(tmp_path, text), root)
    return {entry.line: entry.token for entry in result.entries}


# ---------------------------------------------------------------------------
# The fixture pair: one registry the runner must refuse, one it must not
# ---------------------------------------------------------------------------


def test_fixture_pair_a_row_naming_a_missing_detector_is_a_resolution_error(
    tmp_path: Path,
) -> None:
    """T1, the pair's positive: the runner must fail on this registry."""
    result = _resolve(tmp_path, HEADER + "ZZ-01,zz_gone.py,enforced-and-blocking\n")

    assert result.returncode == 1
    assert _findings(result.stdout) == [
        "finding: line 2: ZZ-01: resolution-error - the detector value "
        f"'zz_gone.py' is not the file name of a Detector in {tmp_path / 'detectors'}"
    ]
    assert _last(result.stdout).startswith("checked 1 row(s) of ")
    assert "clean:" not in result.stdout
    assert "empty:" not in result.stdout


def test_fixture_pair_the_same_row_naming_a_present_detector_is_clean(
    tmp_path: Path,
) -> None:
    """T2, the pair's negative: the runner must not fail on this registry."""
    result = _resolve(tmp_path, HEADER + "ZZ-01,zz_ok.py,enforced-and-blocking\n")

    assert result.returncode == 0
    assert _findings(result.stdout) == []
    assert result.stdout.splitlines() == [_last(result.stdout)]
    assert _last(result.stdout).startswith(f"clean:{SUBJECT} - 1 row(s) of ")
    assert _tokens(tmp_path, HEADER + "ZZ-01,zz_ok.py,\n") == {2: "resolved"}


# ---------------------------------------------------------------------------
# What a detector value means
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("form", ["stem", "relative", "absolute", "case"])
def test_a_value_that_is_not_the_exact_file_name_is_a_resolution_error(
    tmp_path: Path, form: str
) -> None:
    """T3: each of these points at a Detector that exists, and names none."""
    root = _detectors(tmp_path)
    value = {
        "stem": "zz_ok",
        "relative": "sub/zz_deep.py",
        "absolute": str(root / "zz_ok.py"),
        "case": "ZZ_OK.py",
    }[form]

    result = _resolve(tmp_path, HEADER + f"ZZ-01,{value},\n")

    assert result.returncode == 1
    assert len(_findings(result.stdout)) == 1
    assert f"resolution-error - the detector value {value!r} " in result.stdout
    assert detector_runner.resolve_detector(value, ("zz_ok.py", "zz_deep.py")) is None


@pytest.mark.parametrize("name", ["zz_lib.py", "zz_notes.md", "registry.csv"])
def test_a_file_that_exists_and_is_not_a_detector_is_a_resolution_error(
    tmp_path: Path, name: str
) -> None:
    """T4: a module with no command line, a text file, the registry itself."""
    root = _detectors(tmp_path)
    (root / "zz_notes.md").write_text("notes\n", encoding="utf-8")
    text = HEADER + f"ZZ-01,{name},\n"
    (root / "registry.csv").write_text(text, encoding="utf-8")
    assert (root / name).is_file()

    result = _run("--registry", str(root / "registry.csv"), "--detectors", str(root))

    assert result.returncode == 1
    assert len(_findings(result.stdout)) == 1
    assert f"ZZ-01: resolution-error - the detector value {name!r} " in result.stdout


def test_a_program_the_binding_check_skips_is_not_a_detector(tmp_path: Path) -> None:
    """A copy of the tree: the three skipped programs name no Detector there."""
    for path in _DETECTORS_DIR.glob("*.py"):
        shutil.copy(path, tmp_path)
    rows = "".join(
        f"ZZ-{n:02d},{name},\n" for n, name in enumerate(binding_check.SKIPPED_FILES)
    )
    (tmp_path / "constraint-registry.csv").write_text(
        HEADER + rows + "ZZ-09,orphan_check.py,\n", encoding="utf-8"
    )

    result = _run(runner=tmp_path / _RUNNER.name)

    assert result.returncode == 1
    assert len(_findings(result.stdout)) == len(binding_check.SKIPPED_FILES) == 3
    for name in binding_check.SKIPPED_FILES:
        assert f"resolution-error - the detector value {name!r} " in result.stdout
    assert "'orphan_check.py'" not in result.stdout


def test_a_value_with_surrounding_spaces_resolves_and_a_spaces_only_cell_declares_none(
    tmp_path: Path,
) -> None:
    """T6."""
    padded = _resolve(tmp_path, HEADER + "ZZ-01,  zz_ok.py  ,\n")
    blank = _resolve(tmp_path, HEADER + "ZZ-01,   ,not-yet-enforced\n")

    assert padded.returncode == 0
    assert _last(padded.stdout).startswith(f"clean:{SUBJECT} - ")
    assert blank.returncode == 0
    assert _findings(blank.stdout) == []
    assert _last(blank.stdout).startswith(f"empty:{SUBJECT} - ")
    assert detector_runner.resolve_detector(" zz_ok.py ", ("zz_ok.py",)) == "zz_ok.py"
    assert detector_runner.resolve_detector("", ("zz_ok.py", "")) is None


#: File contents that cannot be parsed as Python, so the file may or may not
#: be a Detector.
_NOT_PARSEABLE = {
    "a syntax error": b"def broken(:\n",
    "plain text": b"TODO: write this detector later\n",
    "merge-conflict markers": (
        b"<<<<<<< ours\n"
        + STUB.encode()
        + b"=======\n"
        + STUB.encode()
        + b">>>>>>> theirs\n"
    ),
    "NUL bytes": b"\x00\x00\x00\x00",
    "bytes that are not UTF-8": b"\xff\xfe\n",
}


@pytest.mark.parametrize(
    "content", list(_NOT_PARSEABLE.values()), ids=list(_NOT_PARSEABLE)
)
def test_a_row_naming_a_py_file_that_cannot_be_parsed_makes_the_run_unchecked(
    tmp_path: Path, content: bytes
) -> None:
    """The binding check lists such a file; the runner must not call it resolved."""
    root = _detectors(tmp_path)
    (root / "zz_broken.py").write_bytes(content)

    result = _resolve(tmp_path, HEADER + "ZZ-01,zz_ok.py,\nZZ-02,zz_broken.py,\n")

    assert "zz_broken.py" in binding_check.detector_files(root)
    assert result.returncode == 2
    assert result.stderr == ""
    assert result.stdout.splitlines() == [_last(result.stdout)]
    assert _last(result.stdout).startswith(f"unchecked:{SUBJECT} - ")
    assert "line 3: 'zz_broken.py'" in result.stdout
    assert "line 2" not in result.stdout
    assert "clean:" not in result.stdout


def test_a_row_naming_a_py_file_that_cannot_be_read_makes_the_run_unchecked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _detectors(tmp_path)
    (root / "zz_noread.py").write_text(STUB, encoding="utf-8")
    path = _write(tmp_path, HEADER + "ZZ-01,zz_noread.py,\n")
    read_bytes = Path.read_bytes

    def refuse(self: Path) -> bytes:
        if self.name == "zz_noread.py":
            raise PermissionError("zz-refused")
        return read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", refuse)
    result = detector_runner.enumerate_constraints(path, root)
    status = detector_runner.main(["--registry", str(path), "--detectors", str(root)])

    assert result.status == detector_runner.UNCHECKED
    assert result.entries == ()
    assert status == 2
    out = capsys.readouterr().out
    assert out.startswith(f"unchecked:{SUBJECT} - ")
    assert "line 2: 'zz_noread.py'" in out
    assert "clean:" not in out


def test_an_unparseable_file_and_a_missing_one_together_are_unchecked_not_a_finding(
    tmp_path: Path,
) -> None:
    """Exit 2 wins, and no finding line is printed with it."""
    root = _detectors(tmp_path)
    (root / "zz_broken.py").write_text("def broken(:\n", encoding="utf-8")

    result = _resolve(
        tmp_path, HEADER + "ZZ-01,zz_gone.py,\nZZ-02,  zz_broken.py ,\nZZ-03\n"
    )

    assert result.returncode == 2
    assert _findings(result.stdout) == []
    assert result.stdout.splitlines() == [_last(result.stdout)]
    assert _last(result.stdout).startswith(f"unchecked:{SUBJECT} - ")
    assert "line 3: 'zz_broken.py'" in result.stdout
    assert "the detector field of 1 row(s) " in result.stdout
    assert " - line(s) 4; " in result.stdout


def test_an_unparseable_file_no_row_names_changes_no_outcome(tmp_path: Path) -> None:
    """The control: only a row that names the file makes the run unchecked."""
    root = _detectors(tmp_path)
    (root / "zz_broken.py").write_text("def broken(:\n", encoding="utf-8")

    clean = _resolve(tmp_path, HEADER + "ZZ-01,zz_ok.py,\n")
    missing = _resolve(tmp_path, HEADER + "ZZ-01,zz_gone.py,\n")
    module = _resolve(tmp_path, HEADER + "ZZ-01,zz_lib.py,\n")
    empty = _resolve(tmp_path, HEADER + "ZZ-01,,not-yet-enforced\n")

    assert clean.returncode == 0
    assert _last(clean.stdout).startswith(f"clean:{SUBJECT} - ")
    assert missing.returncode == 1
    assert len(_findings(missing.stdout)) == 1
    assert module.returncode == 1
    assert len(_findings(module.stdout)) == 1
    assert empty.returncode == 0
    assert _last(empty.stdout).startswith(f"empty:{SUBJECT} - ")


# ---------------------------------------------------------------------------
# Rows whose detector field could not be read
# ---------------------------------------------------------------------------


def test_a_short_row_makes_the_run_unchecked_and_names_the_column_and_lines(
    tmp_path: Path,
) -> None:
    """T7, first part: one such row is enough, whatever the other rows hold."""
    alone = _resolve(tmp_path, HEADER + "ZZ-01,zz_ok.py,\nZZ-02\n")
    lines = alone.stdout.splitlines()

    assert alone.returncode == 2
    assert _findings(alone.stdout) == []
    assert len(lines) == 1
    assert lines[0].startswith(
        f"unchecked:{SUBJECT} - the detector field of 1 row(s) of "
    )
    assert lines[0].endswith(" - line(s) 3")

    only = _resolve(tmp_path, HEADER + "ZZ-02\nZZ-03\n")
    assert only.returncode == 2
    assert only.stdout.splitlines() == [_last(only.stdout)]
    assert _last(only.stdout).startswith(
        f"unchecked:{SUBJECT} - the detector field of 2 row(s) of "
    )
    assert _last(only.stdout).endswith(" - line(s) 2, 3")


def test_a_short_row_beside_a_missing_detector_is_unchecked_and_prints_no_finding(
    tmp_path: Path,
) -> None:
    """T7, second part: exit 2 wins over exit 1, and the missing row is not printed."""
    result = _resolve(tmp_path, HEADER + "ZZ-01,zz_gone.py,\nZZ-02\n")

    assert result.returncode == 2
    assert _findings(result.stdout) == []
    assert "zz_gone.py" not in result.stdout
    assert result.stdout.splitlines() == [_last(result.stdout)]
    assert _last(result.stdout).startswith(f"unchecked:{SUBJECT} - ")
    assert _last(result.stdout).endswith(" - line(s) 3")


def test_a_row_with_an_undecodable_detector_field_makes_the_run_unchecked(
    tmp_path: Path,
) -> None:
    _detectors(tmp_path)
    path = tmp_path / "registry.csv"
    path.write_bytes(HEADER.encode() + b"ZZ-01,zz_\xff.py,\n")

    result = _run("--registry", str(path), "--detectors", str(tmp_path / "detectors"))

    assert result.returncode == 2
    assert _findings(result.stdout) == []
    assert result.stdout.splitlines() == [_last(result.stdout)]
    assert _last(result.stdout).startswith(
        f"unchecked:{SUBJECT} - the detector field of 1 row(s) of "
    )
    assert _last(result.stdout).endswith(" - line(s) 2")


_UNREAD_DETECTOR = {
    "short-row": b"ZZ-09\n",
    "not-utf-8": b"ZZ-09,zz_\xff.py,\n",
}
_BESIDE = {
    "alone": b"",
    "rows-that-resolve": b"ZZ-01,zz_ok.py,\nZZ-02,zz_ok.py,enforced-and-blocking\n",
    "a-missing-detector": b"ZZ-01,zz_gone.py,\nZZ-02,zz_ok.py,\n",
}


@pytest.mark.parametrize("beside", sorted(_BESIDE))
@pytest.mark.parametrize("kind", sorted(_UNREAD_DETECTOR))
def test_one_unreadable_detector_cell_makes_the_whole_run_unchecked(
    tmp_path: Path, kind: str, beside: str
) -> None:
    """Whatever the other rows hold, the run says it could not check."""
    root = _detectors(tmp_path)
    path = tmp_path / "registry.csv"
    path.write_bytes(HEADER.encode() + _BESIDE[beside] + _UNREAD_DETECTOR[kind])
    line = 2 + _BESIDE[beside].count(b"\n")

    result = _run("--registry", str(path), "--detectors", str(root))
    built = detector_runner.enumerate_constraints(path, root)

    assert result.returncode == 2
    assert result.stderr == ""
    assert result.stdout.splitlines() == detector_runner.render(built)
    assert built.status == detector_runner.UNCHECKED
    assert built.entries == ()
    assert len(result.stdout.splitlines()) == 1
    assert result.stdout.startswith(f"unchecked:{SUBJECT} - the detector field of ")
    assert result.stdout.endswith(f" - line(s) {line}\n")
    assert _findings(result.stdout) == []
    assert "zz_gone.py" not in result.stdout
    assert not any(
        text.startswith(("clean:", "empty:")) for text in result.stdout.splitlines()
    )


def test_a_line_holding_only_spaces_is_a_row_with_no_detector_field(
    tmp_path: Path,
) -> None:
    """The parser reads it as a one-field row, not as a blank line."""
    text = HEADER + "ZZ-01,zz_ok.py,\n   \n"

    read = registry.read_registry(_write(tmp_path, text))
    result = _resolve(tmp_path, text)

    assert [row.line for row in read.rows] == [2, 3]
    assert read.rows[1].failed(registry.COLUMN_DETECTOR) is not None
    assert result.returncode == 2
    assert result.stdout.splitlines() == [_last(result.stdout)]
    assert _last(result.stdout).startswith(
        f"unchecked:{SUBJECT} - the detector field of 1 row(s) of "
    )
    assert _last(result.stdout).endswith(" - line(s) 3")


def test_a_failure_in_another_column_does_not_stop_a_row_being_resolved(
    tmp_path: Path,
) -> None:
    """T7, third part: a bad state, a shared id and an empty id."""
    text = (
        HEADER + "ZZ-01,zz_ok.py,true\n"
        "ZZ-02,zz_gone.py,true\n"
        "ZZ-03,zz_gone.py,\n"
        "ZZ-03,zz_ok.py,\n"
        ",zz_gone.py,\n"
    )
    result = _resolve(tmp_path, text)

    assert _tokens(tmp_path, text) == {
        2: "resolved",
        3: "resolution-error",
        4: "resolution-error",
        5: "resolved",
        6: "resolution-error",
    }
    assert result.returncode == 1
    assert [line.split(" - ")[0] for line in _findings(result.stdout)] == [
        "finding: line 3: ZZ-02: resolution-error",
        "finding: line 4: (no usable id): resolution-error",
        "finding: line 6: (no usable id): resolution-error",
    ]
    assert not any(line.startswith("unchecked:") for line in result.stdout.splitlines())


# ---------------------------------------------------------------------------
# One enumeration domain: every row of the one registry
# ---------------------------------------------------------------------------


def test_every_row_is_enumerated_whatever_its_id_or_extra_columns(
    tmp_path: Path,
) -> None:
    """T8."""
    text = (
        "id,detector,enforcement_state,owner\n"
        "ZZ-01,zz_ok.py,enforced-and-blocking,a\n"
        "zz.inherited/02,zz_ok.py,enforced-but-non-blocking,b\n"
        '"ZZ, 03",zz_ok.py,,\n'
        "GC-ZZ-04,zz_gone.py,unenforceable,c\n"
        "5,zz_ok.py,not-yet-enforced,d,stray\n"
        "ZZ-06,,not-yet-enforced,e\n"
    )
    result = _resolve(tmp_path, text)

    assert _tokens(tmp_path, text) == {
        2: "resolved",
        3: "resolved",
        4: "resolved",
        5: "resolution-error",
        6: "resolved",
    }
    assert result.returncode == 1
    assert [line.split(" - ")[0] for line in _findings(result.stdout)] == [
        "finding: line 5: GC-ZZ-04: resolution-error"
    ]
    assert _last(result.stdout).startswith("checked 6 row(s) of ")
    assert ", 5 declare a Detector, 1 resolution error(s), " in _last(result.stdout)


def test_worked_example_gives_each_row_its_documented_token(tmp_path: Path) -> None:
    result = _resolve(tmp_path, WORKED_EXAMPLE)
    lines = result.stdout.splitlines()

    assert _tokens(tmp_path, WORKED_EXAMPLE) == {
        2: "resolved",
        3: "resolution-error",
        4: "resolution-error",
        5: "resolution-error",
        6: "resolution-error",
    }
    assert result.returncode == 1
    assert len(_findings(result.stdout)) == 4
    assert lines[4].startswith("checked 6 row(s) of ")
    assert ", 5 declare a Detector, 4 resolution error(s), " in lines[4]
    assert len(lines) == 5


def test_the_runner_runs_no_detector(tmp_path: Path) -> None:
    root = _detectors(tmp_path)
    marker = tmp_path / "ran"
    (root / "zz_ok.py").write_text(
        "from pathlib import Path\n\n"
        'if __name__ == "__main__":\n'
        f"    Path({str(marker)!r}).write_text('ran')\n",
        encoding="utf-8",
    )

    result = _resolve(tmp_path, HEADER + "ZZ-01,zz_ok.py,\n")

    assert result.returncode == 0
    assert not marker.exists()


# ---------------------------------------------------------------------------
# Outcomes: empty is not clean, and could-not-check is neither
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rows", "count"),
    [("", 0), ("ZZ-01,,not-yet-enforced\nZZ-02,,\n", 2)],
    ids=["header-only", "no-row-declares-a-detector"],
)
def test_no_row_declaring_a_detector_reports_empty_and_never_clean(
    tmp_path: Path, rows: str, count: int
) -> None:
    """T9."""
    result = _resolve(tmp_path, HEADER + rows)

    assert result.returncode == 0
    assert result.stdout.splitlines() == [_last(result.stdout)]
    assert _last(result.stdout).startswith(f"empty:{SUBJECT} - {count} row(s) of ")
    assert ", 0 declare a Detector, 0 resolution error(s), " in result.stdout
    assert "clean" not in result.stdout


def test_a_missing_registry_is_unchecked_and_exits_two(tmp_path: Path) -> None:
    """T10, first part."""
    root = _detectors(tmp_path)
    missing = tmp_path / "absent.csv"

    result = _run("--registry", str(missing), "--detectors", str(root))

    assert result.returncode == 2
    assert result.stdout == f"unchecked:{SUBJECT} - no file at {missing}\n"


@pytest.mark.parametrize(
    "text",
    ["", "id,detector\nZZ-01,zz_ok.py\n", HEADER + 'ZZ-01,"zz_ok.py,\n'],
    ids=["zero-bytes", "header-missing-a-column", "quote-never-closed"],
)
def test_a_registry_the_reader_refuses_whole_is_unchecked(
    tmp_path: Path, text: str
) -> None:
    result = _resolve(tmp_path, text)

    assert result.returncode == 2
    assert result.stdout.startswith(f"unchecked:{SUBJECT} - ")
    assert len(result.stdout.splitlines()) == 1


def test_a_registry_path_that_is_a_directory_is_unchecked(tmp_path: Path) -> None:
    root = _detectors(tmp_path)

    result = _run("--registry", str(root), "--detectors", str(root))

    assert result.returncode == 2
    assert result.stdout.startswith(f"unchecked:{SUBJECT} - ")


@pytest.mark.parametrize(
    "rows",
    ["", "ZZ-01,,not-yet-enforced\n", "ZZ-01,zz_ok.py,\n"],
    ids=["header-only", "no-row-declares-a-detector", "a-row-declares-one"],
)
@pytest.mark.parametrize("kind", ["absent", "a-file"])
def test_a_detectors_directory_that_cannot_be_listed_is_unchecked_on_every_run(
    tmp_path: Path, rows: str, kind: str
) -> None:
    """T10, second part: a mistyped --detectors never passes as empty."""
    target = tmp_path / "zz_mistyped"
    if kind == "a-file":
        target.write_text(STUB, encoding="utf-8")

    result = _run(
        "--registry", str(_write(tmp_path, HEADER + rows)), "--detectors", str(target)
    )

    assert result.returncode == 2
    assert result.stdout == (
        f"unchecked:{SUBJECT} - the detectors directory {target} is not a "
        "directory or could not be listed\n"
    )


def test_a_failure_inside_the_run_is_returned_as_unchecked_and_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _detectors(tmp_path)
    path = _write(tmp_path, HEADER + "ZZ-01,zz_gone.py,\n")

    def boom(_root: Path) -> tuple[str, ...]:
        raise RuntimeError("zz-boom")

    monkeypatch.setattr(binding_check, "detector_files", boom)
    result = detector_runner.enumerate_constraints(path, root)
    status = detector_runner.main(["--registry", str(path), "--detectors", str(root)])

    assert result.status == detector_runner.UNCHECKED
    assert result.entries == ()
    assert status == 2
    assert capsys.readouterr().out == (
        f"unchecked:{SUBJECT} - the run itself failed: RuntimeError: zz-boom\n"
    )


def test_a_wrong_command_line_exits_two(tmp_path: Path) -> None:
    result = _run("--no-such-option")

    assert result.returncode == 2
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# The exit status
# ---------------------------------------------------------------------------

#: What the written description of the runner's exit status must say, in
#: its module docstring and in its README section, read as plain text.
_EXIT_STATUS_STATEMENTS = (
    "Exit status 1 means a missing Detector only on a run that finished",
    "A crash of the runner itself also exits 1",
    "A check that cannot write its answer is also unchecked, with exit status 2",
    "The runner does this",
    "The orphan check, the binding check and the report do not yet",
    "0, 1 or 2, and the report only 0 or 2",
    "exits 120",
)


def _plain(text: str) -> str:
    """*text* on one line, without the marks that set a word as code."""
    return " ".join(text.replace("`", "").split())


@pytest.mark.parametrize("statement", _EXIT_STATUS_STATEMENTS)
def test_the_written_exit_status_description_says_what_is_true(
    statement: str,
) -> None:
    readme = (_DETECTORS_DIR / "README.md").read_text(encoding="utf-8")
    section = readme[readme.index("## The detector runner") :]

    assert statement in _plain(detector_runner.__doc__)
    assert statement in _plain(section)


def test_no_check_is_described_as_returning_no_other_value() -> None:
    """Three checks exit 120 on a full output device, so the sentence is not true."""
    readme = _plain((_DETECTORS_DIR / "README.md").read_text(encoding="utf-8"))

    assert "no other value" not in readme
    assert readme.count("does not yet return 2 when it cannot write its output") == 3


_EXIT_CASES = {
    "missing-detector": (HEADER + "ZZ-01,zz_gone.py,\n", 1),
    "present-detector": (HEADER + "ZZ-01,zz_ok.py,\n", 0),
    "short-row-alone": (HEADER + "ZZ-01\n", 2),
    "short-row-beside-missing": (HEADER + "ZZ-01\nZZ-02,zz_gone.py,\n", 2),
    "header-only": (HEADER, 0),
    "no-row-declares": (HEADER + "ZZ-01,,\n", 0),
    "registry-refused": ("id,detector\n", 2),
}


@pytest.mark.parametrize("case", sorted(_EXIT_CASES))
def test_exit_one_if_and_only_if_a_resolution_error_line_was_printed(
    tmp_path: Path, case: str
) -> None:
    """T11."""
    text, expected = _EXIT_CASES[case]

    result = _resolve(tmp_path, text)
    printed = any(
        line.startswith("finding:") and ": resolution-error - " in line
        for line in result.stdout.splitlines()
    )

    assert result.returncode == expected
    assert (result.returncode == 1) == printed
    assert result.stdout.endswith("\n")


def test_the_exit_status_comes_from_the_one_mapping_function(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """T11: main returns what exit_status returns, for the result it printed."""
    root = _detectors(tmp_path)
    path = _write(tmp_path, HEADER + "ZZ-01,zz_gone.py,\n")
    seen = []

    def mapping(result, written=True):
        seen.append((result, written))
        return 7

    result = detector_runner.enumerate_constraints(path, root)
    assert detector_runner.exit_status(result) == 1
    assert detector_runner.exit_status(result, written=False) == 2
    clean = detector_runner.enumerate_constraints(
        _write(tmp_path, HEADER + "ZZ-01,zz_ok.py,\n"), root
    )
    assert detector_runner.exit_status(clean) == 0
    assert detector_runner.exit_status(clean, written=False) == 2

    path = _write(tmp_path, HEADER + "ZZ-01,zz_gone.py,\n")
    monkeypatch.setattr(detector_runner, "exit_status", mapping)
    status = detector_runner.main(["--registry", str(path), "--detectors", str(root)])

    assert status == 7
    assert seen == [(result, True)]
    assert capsys.readouterr().out.splitlines() == detector_runner.render(result)


def _run_with_stdout(tmp_path: Path, text: str, how: str) -> int:
    root = tmp_path / "detectors"
    if not root.exists():
        _detectors(tmp_path)
    command = [
        *(sys.executable, "-B", str(_RUNNER)),
        *("--registry", str(_write(tmp_path, text)), "--detectors", str(root)),
    ]
    if how == "closed":
        done = subprocess.run(
            command, stderr=subprocess.PIPE, preexec_fn=lambda: os.close(1)
        )
    else:
        with open("/dev/full", "w") as full:
            done = subprocess.run(command, stdout=full, stderr=subprocess.PIPE)
    return done.returncode


@pytest.mark.parametrize("how", ["closed", "full"])
@pytest.mark.parametrize(
    "rows",
    ["ZZ-01,zz_ok.py,\n", "ZZ-01,zz_gone.py,\n", ""],
    ids=["clean", "error", "empty"],
)
def test_output_that_could_not_be_written_exits_two_whatever_was_decided(
    tmp_path: Path, rows: str, how: str
) -> None:
    """A run nobody could read is not a pass, and not a resolution error."""
    assert _run_with_stdout(tmp_path, HEADER + rows, how) == 2


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def test_an_id_or_a_detector_value_holding_a_control_character_cannot_forge_a_line(
    tmp_path: Path,
) -> None:
    """The parser keeps these in the cell; printed raw, each could forge a line."""
    forged = f"clean:{SUBJECT} - forged"
    text = (
        HEADER + f'"ZZ-01\u2028{forged}","zz_gone.py\u2028{forged}",\n'
        f'"ZZ-02\x1b[2K{forged}","zz_ok.py\x1b[2K\u2028{forged}",\n'
    )
    result = _resolve(tmp_path, text)
    lines = result.stdout.split("\n")

    assert result.returncode == 1
    assert lines[-1] == ""
    assert len(lines) == 4
    assert lines[0].startswith("finding: line 2: ZZ-01\\u2028clean:")
    assert lines[1].startswith("finding: line 3: ZZ-02\\x1b[2Kclean:")
    assert "'zz_gone.py\\u2028clean:" in lines[0]
    assert "\\x1b[2K\\u2028clean:" in lines[1]
    assert lines[2].startswith("checked 2 row(s) of ")
    assert not any(line.startswith("clean:") for line in result.stdout.splitlines())
    assert "\x1b" not in result.stdout
    assert "\u2028" not in result.stdout


_FORGED = f"clean:{SUBJECT} - forged"

#: Registries holding a line break in a cell. In the last, read leniently,
#: lines 3 and 4 vanish into the cell opened on line 2: a row naming a missing
#: Detector is hidden and the run reports that no row declares one.
_LINE_BREAK_IN_A_CELL = {
    "a-line-feed-in-an-id-and-a-detector-value": (
        HEADER + f'"ZZ-01\n{_FORGED}","zz_gone.py\n{_FORGED}",\n'
    ),
    "a-carriage-return-in-an-id": HEADER + f'"ZZ-02\r{_FORGED}",zz_ok.py,\n',
    "rows-between-two-quotes": (
        "id,detector,enforcement_state,note\n"
        'ZZ-01,,not-yet-enforced,"zz note\n'
        "ZZ-02,zz_gone.py,enforced-and-blocking,\n"
        'ZZ-03,,,"\n'
        "ZZ-04,,unenforceable,\n"
    ),
}


@pytest.mark.parametrize("case", sorted(_LINE_BREAK_IN_A_CELL))
def test_a_registry_cell_holding_a_line_break_is_unchecked_and_exits_two(
    tmp_path: Path, case: str
) -> None:
    result = _resolve(tmp_path, _LINE_BREAK_IN_A_CELL[case])
    lines = result.stdout.split("\n")

    assert result.returncode == 2
    assert len(lines) == 2
    assert lines[-1] == ""
    assert lines[0].startswith(f"unchecked:{SUBJECT} - ")
    assert "holds a line break inside a cell" in lines[0]
    assert _findings(result.stdout) == []
    assert not any(
        line.startswith(("clean:", "empty:")) for line in result.stdout.splitlines()
    )
    assert "\r" not in result.stdout


def test_a_path_holding_a_line_break_cannot_forge_a_line(tmp_path: Path) -> None:
    forged = f"clean:{SUBJECT} - forged"
    root = tmp_path / f"zz\n{forged}"
    root.mkdir()
    (root / "zz_ok.py").write_text(STUB, encoding="utf-8")
    path = root / "registry.csv"
    cases = {
        2: None,
        0: HEADER + "ZZ-01,zz_ok.py,\n",
        1: HEADER + "ZZ-01,zz_gone.py,\n",
    }

    for expected, text in cases.items():
        if text is not None:
            path.write_text(text, encoding="utf-8")
        result = _run("--registry", str(path), "--detectors", str(root))
        absent = _run("--registry", str(tmp_path / "r.csv"), "--detectors", str(root))

        assert result.returncode == expected
        assert not any(
            line.startswith(forged)
            for line in (result.stdout + absent.stdout).split("\n")
        )
        assert len(result.stdout.split("\n")) == (3 if expected == 1 else 2)
        assert absent.returncode == 2
        assert len(absent.stdout.split("\n")) == 2


@pytest.mark.parametrize(
    "rows",
    ["", "ZZ-01,zz_ok.py,\n", "ZZ-01,zz_gone.py,\n"],
    ids=["empty", "clean", "findings"],
)
def test_the_line_carrying_the_counts_says_what_was_not_looked_at(
    tmp_path: Path, rows: str
) -> None:
    last = _last(_resolve(tmp_path, HEADER + rows).stdout)

    assert str(tmp_path / "registry.csv") in last
    assert str(tmp_path / "detectors") in last
    assert "does not run any Detector" in last
    assert "does not check fixture pairs" in last
    assert "does not compare the registry with the constraint files on disk" in last
    assert "a Constraint with no row is not seen" in last


def test_the_result_is_immutable_and_carries_what_the_lines_are_built_from(
    tmp_path: Path,
) -> None:
    root = _detectors(tmp_path)
    path = _write(tmp_path, WORKED_EXAMPLE)

    result = detector_runner.enumerate_constraints(path, root)
    first, second = result.entries[:2]

    assert result.status == detector_runner.CHECKED
    assert result.rows_read == 6
    assert (first.line, first.id, first.value, first.token, first.file_name) == (
        2,
        "ZZ-01",
        "zz_ok.py",
        "resolved",
        "zz_ok.py",
    )
    assert (second.token, second.file_name) == ("resolution-error", None)
    assert result.entries[-1].value == "zz_lib.py"
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.status = "clean"
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.token = "resolved"
    empty = detector_runner.enumerate_constraints(_write(tmp_path, HEADER), root)
    assert (empty.status, empty.entries, empty.rows_read) == ("empty", (), 0)


# ---------------------------------------------------------------------------
# Defaults, and independence from everything but the two siblings
# ---------------------------------------------------------------------------


def test_the_defaults_are_the_registry_and_the_directory_beside_the_runner(
    tmp_path: Path,
) -> None:
    for name in _MODULES:
        shutil.copy(_DETECTORS_DIR / f"{name}.py", tmp_path)
    copied = tmp_path / _RUNNER.name
    (tmp_path / "zz_ok.py").write_text(STUB, encoding="utf-8")

    absent = _run(runner=copied)
    (tmp_path / "constraint-registry.csv").write_text(
        HEADER + "ZZ-01,zz_ok.py,\nZZ-02,zz_gone.py,\n", encoding="utf-8"
    )
    result = _run(runner=copied)

    assert absent.returncode == 2
    assert absent.stdout == (
        f"unchecked:{SUBJECT} - no file at {tmp_path / 'constraint-registry.csv'}\n"
    )
    assert result.returncode == 1
    assert _findings(result.stdout) == [
        "finding: line 3: ZZ-02: resolution-error - the detector value "
        f"'zz_gone.py' is not the file name of a Detector in {tmp_path}"
    ]
    assert not (tmp_path / "__pycache__").exists()


# ---------------------------------------------------------------------------
# Agreement with the enforcement report
# ---------------------------------------------------------------------------


def test_the_runner_and_the_report_agree_on_a_row_naming_a_missing_detector(
    tmp_path: Path,
) -> None:
    """T12: two commands on one tree, compared on exit codes and tokens only."""
    root = _detectors(tmp_path)
    path = _write(tmp_path, HEADER + "ZZ-01,,not-yet-enforced\nZZ-02,zz_gone.py,\n")
    args = ("--registry", str(path), "--detectors", str(root))

    runner = _run(*args)
    report = _run(*args, runner=_REPORT)
    lowered = [line for line in report.stdout.splitlines() if "lowered" in line]

    assert runner.returncode == 1
    assert _findings(runner.stdout)[0].startswith(
        "finding: line 3: ZZ-02: resolution-error - "
    )
    assert report.returncode == 0
    assert len(lowered) == 1
    assert "not-found" in lowered[0]
    assert "line 3" in lowered[0]


# ---------------------------------------------------------------------------
# The shipped tree
# ---------------------------------------------------------------------------


def _bytecode() -> set[Path]:
    return set(_DETECTORS_DIR.rglob("__pycache__"))


@pytest.mark.process
def test_shipped_registry_has_nothing_to_resolve_and_reports_empty() -> None:
    """T13, first part: the runner with no arguments."""
    # Loading the modules above may already have written bytecode there, so
    # the run is compared with what was there before it.
    before = _bytecode()
    # Without this variable in the way, only -B keeps bytecode out of the tree.
    env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}

    result = _run(env=env)

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.splitlines() == [_last(result.stdout)]
    assert _last(result.stdout).startswith(f"empty:{SUBJECT} - 0 row(s) of ")
    assert _bytecode() <= before, "the run wrote bytecode into the product tree"


@pytest.mark.process
def test_shipped_detectors_directory_resolves_the_orphan_check_and_nothing_else(
    tmp_path: Path,
) -> None:
    """T13, second part: a registry on tmp_path against the shipped Detectors."""
    present = _run(
        "--registry", str(_write(tmp_path, HEADER + "ZZ-01,orphan_check.py,\n"))
    )
    others = sorted(
        p.name for p in _DETECTORS_DIR.glob("*.py") if p.name != "orphan_check.py"
    )
    rows = "".join(f"ZZ-{n:02d},{name},\n" for n, name in enumerate(others))
    absent = _run("--registry", str(_write(tmp_path, HEADER + rows)))

    assert present.returncode == 0
    assert _last(present.stdout).startswith(f"clean:{SUBJECT} - 1 row(s) of ")
    assert _RUNNER.name in others
    assert len(others) == 4
    assert absent.returncode == 1
    assert len(_findings(absent.stdout)) == len(others)


@pytest.mark.process
def test_the_binding_check_skips_the_runner_as_it_skips_itself() -> None:
    """T13, third part: the binding check with no arguments."""
    result = subprocess.run(
        [sys.executable, "-B", str(_BINDING_CHECK)], capture_output=True, text=True
    )
    reported = [
        line
        for line in result.stdout.splitlines()
        if line.startswith(("finding:", "detector:"))
    ]

    assert _RUNNER.name in binding_check.SKIPPED_FILES
    assert result.returncode == 0
    assert reported == ["detector: orphan_check.py: functional"]
    assert _RUNNER.name in _last(result.stdout)
    assert " were not checked and are not counted" in _last(result.stdout)
    assert _RUNNER.name not in binding_check.detector_files(_DETECTORS_DIR)


def test_the_third_skip_is_by_path_and_not_by_name(tmp_path: Path) -> None:
    """The same file name in another directory is an ordinary file there."""
    (tmp_path / _RUNNER.name).write_text(STUB, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-B", str(_BINDING_CHECK), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert f"finding: {_RUNNER.name}: unbound - " in result.stdout
    assert binding_check.detector_files(tmp_path) == (_RUNNER.name,)

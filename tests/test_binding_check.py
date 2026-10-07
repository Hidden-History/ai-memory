"""Tests for the binding check.

The check proves each Detector against a fixture pair: one fixture the
Detector must flag and one it must not. A Detector with no pair, or one
that cannot fail, is reported and the check exits non-zero.

Every case except the shipped pair is built on ``tmp_path``, with stub
Detectors written by the test and synthetic identifiers. No stub is
committed.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from memory.degraded import POV_TREE

_ROOT = Path(__file__).resolve().parent.parent
_POV = _ROOT / POV_TREE
_DETECTORS_DIR = _POV / "detectors"
_CHECK = _DETECTORS_DIR / "binding_check.py"
_SHIPPED_FIXTURES = _DETECTORS_DIR / "fixtures"

_spec = importlib.util.spec_from_file_location("binding_check", _CHECK)
binding_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(binding_check)

STANDING_EXEMPTIONS = (
    "labelled-evidentiary-quotation",
    "historical-record-not-to-inherit",
)

FLAG = "ZZ-FLAG"

#: Exits 1 when the file it is given holds FLAG, else 0.
STUB = f"""import sys

if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as handle:
        sys.exit(1 if "{FLAG}" in handle.read() else 0)
"""


def _always(code: int) -> str:
    return f'import sys\n\nif __name__ == "__main__":\n    sys.exit({code})\n'


RAISES = 'if __name__ == "__main__":\n    raise RuntimeError("zz-stub-crash")\n'

#: Leaves a file beside itself when it is run, so a test can see that it was.
LEAVES_A_TRACE = """import sys
from pathlib import Path

if __name__ == "__main__":
    Path(__file__).with_suffix(".ran").write_text("ran", encoding="utf-8")
    sys.exit(1)
"""


def _detector(root: Path, name: str, source: str = STUB) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}.py"
    path.write_text(source, encoding="utf-8")
    return path


def _manifest(**changes: object) -> dict[str, object]:
    manifest: dict[str, object] = {
        "fixture_marker": "synthetic-fixture",
        "args": ["{fixture}"],
        "positive": "positive.txt",
        "negative": "negative.txt",
        "exemptions": {},
    }
    manifest.update(changes)
    return manifest


def _pair(
    root: Path,
    name: str,
    manifest: object = None,
    files: dict[str, str] | None = None,
    drop: tuple[str, ...] = (),
) -> Path:
    """Write the pair directory for *name*; *drop* removes manifest keys."""
    pair = root / "fixtures" / name
    pair.mkdir(parents=True, exist_ok=True)
    if files is None:
        files = {"positive.txt": f"{FLAG}\n", "negative.txt": "zz-quiet\n"}
    for relative, text in files.items():
        target = pair / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    if manifest is None:
        manifest = _manifest()
    if isinstance(manifest, dict):
        manifest = {k: v for k, v in manifest.items() if k not in drop}
        manifest = json.dumps(manifest)
    (pair / "fixture-pair.json").write_text(str(manifest), encoding="utf-8")
    return pair


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_CHECK), *args], capture_output=True, text=True
    )


def _run_root(root: Path) -> subprocess.CompletedProcess[str]:
    return _run("--root", str(root))


def _findings(out: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith("finding:")]


def _tokens(root: Path) -> dict[str, str]:
    return {d.name: d.token for d in binding_check.check_bindings(root).detectors}


def _one(root: Path, name: str = "zz_stub"):
    result = binding_check.check_bindings(root)
    (entry,) = [d for d in result.detectors if d.name == name]
    return result, entry


# ---------------------------------------------------------------------------
# The check's own fixture pair: T1 must flag, T3 must not
# ---------------------------------------------------------------------------


def test_fixture_pair_a_detector_with_no_pair_is_unbound_and_refused(
    tmp_path: Path,
) -> None:
    """The check's own pair, must-flag (T1)."""
    _detector(tmp_path, "zz_stub")

    result = _run_root(tmp_path)

    assert result.returncode == 1
    (finding,) = _findings(result.stdout)
    assert finding.startswith("finding: zz_stub.py: unbound - ")
    assert "clean:" not in result.stdout
    assert _tokens(tmp_path) == {"zz_stub": "unbound"}


def test_fixture_pair_a_detector_with_a_working_pair_is_functional(
    tmp_path: Path,
) -> None:
    """The check's own pair, must-not-flag (T3)."""
    _detector(tmp_path, "zz_stub")
    _pair(tmp_path, "zz_stub")

    result = _run_root(tmp_path)

    assert result.returncode == 0
    assert _findings(result.stdout) == []
    assert "detector: zz_stub.py: functional" in result.stdout.splitlines()
    assert result.stdout.splitlines()[-1].startswith("clean:fixture-binding - ")
    assert _tokens(tmp_path) == {"zz_stub": "functional"}


# ---------------------------------------------------------------------------
# AC-1: no pair, no binding
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", ["no-manifest", "no-negative", "positive-file-absent"])
def test_half_a_pair_is_unbound(tmp_path: Path, case: str) -> None:
    """T2."""
    _detector(tmp_path, "zz_stub")
    if case == "no-manifest":
        (tmp_path / "fixtures" / "zz_stub").mkdir(parents=True)
    elif case == "no-negative":
        _pair(tmp_path, "zz_stub", drop=("negative",))
    else:
        _pair(tmp_path, "zz_stub", files={"negative.txt": "zz-quiet\n"})

    result, entry = _one(tmp_path)

    assert entry.token == "unbound"
    assert binding_check.exit_status(result) == 1
    assert _run_root(tmp_path).returncode == 1


def test_only_programs_directly_in_the_directory_are_detectors(
    tmp_path: Path,
) -> None:
    """T11: no enumeration of modules, of fixtures/ or of sub-directories."""
    _detector(tmp_path, "zz_stub")
    _pair(tmp_path, "zz_stub")
    _detector(tmp_path, "zz_module", "ZZ_VALUE = 1\n")
    _detector(
        tmp_path,
        "zz_nested_main",
        "def f():\n    if __name__ == '__main__':\n        pass\n",
    )
    _detector(tmp_path / "fixtures", "zz_in_fixtures")
    _detector(tmp_path / "fixtures" / "zz_stub", "zz_in_pair")
    _detector(tmp_path / "zz_subdir", "zz_in_subdir")

    result = _run_root(tmp_path)

    assert _tokens(tmp_path) == {"zz_stub": "functional"}
    assert binding_check.detector_files(tmp_path) == ("zz_stub.py",)
    assert result.returncode == 0
    for name in ("zz_module", "zz_nested_main", "zz_in_fixtures", "zz_in_pair"):
        assert name not in result.stdout
    assert "zz_in_subdir" not in result.stdout


def test_the_self_skip_is_by_path_and_the_output_says_what_was_skipped(
    tmp_path: Path,
) -> None:
    """T20: a copy of the check elsewhere is an ordinary Detector file."""
    shutil.copy(_CHECK, tmp_path / _CHECK.name)

    result = _run_root(tmp_path)

    assert result.returncode == 1
    assert _findings(result.stdout)[0].startswith(f"finding: {_CHECK.name}: unbound - ")

    shipped = _run().stdout
    assert f"{_CHECK.name}" in shipped.splitlines()[-1]
    assert "not checked" in shipped.splitlines()[-1]


def test_the_skipped_files_are_one_tuple_and_the_sentence_is_built_from_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (
        "detector_runner.py",
        _CHECK.name,
        "enforcement_report.py",
    ) == binding_check.SKIPPED_FILES

    monkeypatch.setattr(
        binding_check, "SKIPPED_FILES", (_CHECK.name, "zz_also_skipped.py")
    )
    line = binding_check.render(binding_check.check_bindings(tmp_path))[-1]

    assert f"{_CHECK.name} and zz_also_skipped.py" in line


# ---------------------------------------------------------------------------
# AC-2: the pair must be able to fail
# ---------------------------------------------------------------------------


def test_a_detector_that_passes_on_both_fixtures_is_non_functional(
    tmp_path: Path,
) -> None:
    """T4."""
    _detector(tmp_path, "zz_stub", _always(0))
    _pair(tmp_path, "zz_stub")

    result = _run_root(tmp_path)

    assert result.returncode == 1
    assert _findings(result.stdout)[0].startswith(
        "finding: zz_stub.py: non-functional - "
    )
    assert _tokens(tmp_path) == {"zz_stub": "non-functional"}


def test_a_detector_that_flags_its_negative_is_a_false_positive(
    tmp_path: Path,
) -> None:
    """T5, first half."""
    _detector(tmp_path, "zz_stub", _always(1))
    _pair(tmp_path, "zz_stub")

    _, entry = _one(tmp_path)

    assert entry.token == "false-positive:negative"
    assert entry.named == "negative"
    assert _run_root(tmp_path).returncode == 1
    assert _findings(_run_root(tmp_path).stdout)[0].startswith(
        "finding: zz_stub.py: false-positive:negative - "
    )


def test_a_detector_that_flags_a_declared_exemption_is_a_false_positive(
    tmp_path: Path,
) -> None:
    """T5, second half."""
    _detector(tmp_path, "zz_stub")
    _pair(
        tmp_path,
        "zz_stub",
        manifest=_manifest(exemptions={"zz-quoted": "quoted.txt"}),
        files={
            "positive.txt": f"{FLAG}\n",
            "negative.txt": "zz-quiet\n",
            "quoted.txt": f'kept as evidence: "{FLAG}"\n',
        },
    )

    result, entry = _one(tmp_path)

    assert entry.token == "false-positive:zz-quoted"
    assert entry.named == "zz-quoted"
    assert binding_check.exit_status(result) == 1


def test_a_declared_exemption_the_detector_does_not_fire_on_is_functional(
    tmp_path: Path,
) -> None:
    _detector(tmp_path, "zz_stub")
    _pair(
        tmp_path,
        "zz_stub",
        manifest=_manifest(exemptions={"zz-quoted": "sub/quoted.txt"}),
        files={
            "positive.txt": f"{FLAG}\n",
            "negative.txt": "zz-quiet\n",
            "sub/quoted.txt": "zz-quiet too\n",
        },
    )

    assert _tokens(tmp_path) == {"zz_stub": "functional"}


@pytest.mark.parametrize(
    "source", [_always(2), RAISES, "def broken(:\n"], ids=["exit-2", "raises", "syntax"]
)
def test_a_detector_that_cannot_be_run_is_unchecked_and_exits_two(
    tmp_path: Path, source: str
) -> None:
    """T6: a crash is neither "it failed, so it works" nor a false positive."""
    _detector(tmp_path, "zz_stub", source)
    _pair(tmp_path, "zz_stub")

    result = _run_root(tmp_path)
    tokens = _tokens(tmp_path)

    assert tokens == {"zz_stub": "unchecked:zz_stub"}
    assert result.returncode == 2
    assert _findings(result.stdout) == []
    assert result.stdout.splitlines()[-1].startswith("unchecked:fixture-binding - ")
    assert "functional" not in result.stdout
    assert "false-positive" not in result.stdout
    assert "clean:" not in result.stdout


def test_a_detector_that_crashes_on_its_positive_only_is_not_functional(
    tmp_path: Path,
) -> None:
    """A crash exits 1, as a finding does. It must not count as one."""
    source = STUB.replace("sys.exit(1 if", "sys.exit(1 // 0 if")
    assert source != STUB
    _detector(tmp_path, "zz_stub", source)
    _pair(tmp_path, "zz_stub")

    assert _tokens(tmp_path) == {"zz_stub": "unchecked:zz_stub"}
    assert _run_root(tmp_path).returncode == 2


def test_a_detector_that_flags_and_writes_to_stderr_is_still_read_as_flagging(
    tmp_path: Path,
) -> None:
    """The other side of the crash rule: an ordinary exit 1 is a finding."""
    source = STUB.replace(
        "    with open(", '    print("zz-flagged", file=sys.stderr)\n    with open('
    )
    assert source != STUB
    _detector(tmp_path, "zz_stub", source)
    _pair(tmp_path, "zz_stub")

    assert _tokens(tmp_path) == {"zz_stub": "functional"}


def test_a_finding_beside_an_unchecked_detector_still_exits_one(
    tmp_path: Path,
) -> None:
    _detector(tmp_path, "zz_crash", _always(2))
    _pair(tmp_path, "zz_crash")
    _detector(tmp_path, "zz_unbound")

    result = _run_root(tmp_path)

    assert result.returncode == 1
    assert len(_findings(result.stdout)) == 1
    assert "detector: zz_crash.py: unchecked:zz_crash - " in result.stdout


def test_a_detector_that_runs_past_the_limit_is_unchecked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _detector(
        tmp_path,
        "zz_stub",
        'import time\n\nif __name__ == "__main__":\n    time.sleep(30)\n',
    )
    _pair(tmp_path, "zz_stub")
    monkeypatch.setattr(binding_check, "RUN_TIMEOUT_SECONDS", 0.5)

    assert _tokens(tmp_path) == {"zz_stub": "unchecked:zz_stub"}


# ---------------------------------------------------------------------------
# AC-3 and AC-4: what a manifest must declare
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", ["no-key", "fixture-absent", "not-an-object"])
def test_an_undeclared_or_unprovable_exemption_set_is_refused(
    tmp_path: Path, case: str
) -> None:
    """T7."""
    _detector(tmp_path, "zz_stub")
    if case == "no-key":
        _pair(tmp_path, "zz_stub", drop=("exemptions",))
    elif case == "fixture-absent":
        _pair(tmp_path, "zz_stub", _manifest(exemptions={"zz-quoted": "absent.txt"}))
    else:
        _pair(tmp_path, "zz_stub", _manifest(exemptions=["zz-quoted"]))

    result, entry = _one(tmp_path)

    assert entry.token == "refused:exemptions"
    assert entry.named == "exemptions"
    assert binding_check.exit_status(result) == 1


@pytest.mark.parametrize(
    ("reserved", "files"),
    [
        # The stub flags its own negative; the exemption points at a quiet file.
        (
            "negative",
            {
                "positive.txt": f"{FLAG}\n",
                "negative.txt": f"{FLAG}\n",
                "other.txt": "zz-quiet\n",
            },
        ),
        # The stub does not flag its positive; the exemption points at one it does.
        (
            "positive",
            {
                "positive.txt": "zz-quiet\n",
                "negative.txt": "zz-quiet\n",
                "other.txt": f"{FLAG}\n",
            },
        ),
    ],
    ids=["negative", "positive"],
)
def test_an_exemption_cannot_take_the_name_of_a_fixture_of_the_pair(
    tmp_path: Path, reserved: str, files: dict[str, str]
) -> None:
    """An exemption named like a fixture must not be run in that fixture's place."""
    _detector(tmp_path, "zz_stub")
    _pair(
        tmp_path,
        "zz_stub",
        manifest=_manifest(exemptions={reserved: "other.txt"}),
        files=files,
    )

    result, entry = _one(tmp_path)
    done = _run_root(tmp_path)

    assert entry.token == "refused:exemptions"
    assert entry.named == "exemptions"
    assert reserved in entry.reason
    assert binding_check.exit_status(result) == 1
    assert done.returncode == 1
    assert _findings(done.stdout)[0].startswith(
        "finding: zz_stub.py: refused:exemptions - "
    )


@pytest.mark.parametrize("case", ["absent", "another-value"])
def test_a_pair_without_the_fixture_marker_is_refused(
    tmp_path: Path, case: str
) -> None:
    """T8."""
    _detector(tmp_path, "zz_stub")
    if case == "absent":
        _pair(tmp_path, "zz_stub", drop=("fixture_marker",))
    else:
        _pair(tmp_path, "zz_stub", _manifest(fixture_marker="fixture"))

    result = _run_root(tmp_path)

    assert _tokens(tmp_path) == {"zz_stub": "refused:fixture_marker"}
    assert result.returncode == 1
    assert _findings(result.stdout)[0].startswith(
        "finding: zz_stub.py: refused:fixture_marker - "
    )


@pytest.mark.parametrize(
    "args", [None, "{fixture}", [], ["--zz"], ["{fixture}", 3]], ids=repr
)
def test_args_that_cannot_feed_a_fixture_are_refused(
    tmp_path: Path, args: object
) -> None:
    _detector(tmp_path, "zz_stub")
    if args is None:
        _pair(tmp_path, "zz_stub", drop=("args",))
    else:
        _pair(tmp_path, "zz_stub", _manifest(args=args))

    assert _tokens(tmp_path) == {"zz_stub": "refused:args"}


@pytest.mark.parametrize("case", ["absolute", "dot-dot", "symlink-out"])
def test_a_fixture_path_outside_the_pair_directory_is_refused_and_not_run(
    tmp_path: Path, case: str
) -> None:
    """T9: the fixture exists and would be flagged, and is still refused."""
    root = tmp_path / "detectors"
    detector = _detector(root, "zz_stub", LEAVES_A_TRACE)
    outside = tmp_path / "outside.txt"
    outside.write_text(f"{FLAG}\n", encoding="utf-8")
    pair = _pair(root, "zz_stub")
    if case == "absolute":
        positive = str(outside)
    elif case == "dot-dot":
        positive = "../../../outside.txt"
        assert (pair / positive).exists()
    else:
        (pair / "link.txt").symlink_to(outside)
        positive = "link.txt"
    _pair(root, "zz_stub", _manifest(positive=positive))

    result = _run_root(root)

    assert _tokens(root) == {"zz_stub": "refused:positive"}
    assert result.returncode == 1
    assert not detector.with_suffix(".ran").exists()


def test_the_stub_that_leaves_a_trace_does_leave_one_when_it_is_run(
    tmp_path: Path,
) -> None:
    """Positive control for the "is not run" assertion above."""
    detector = _detector(tmp_path, "zz_stub", LEAVES_A_TRACE)
    _pair(tmp_path, "zz_stub")

    assert _tokens(tmp_path) == {"zz_stub": "false-positive:negative"}
    assert detector.with_suffix(".ran").exists()


@pytest.mark.parametrize(
    "text", ["{not json", '["positive.txt"]', '"synthetic-fixture"', ""]
)
def test_a_manifest_that_is_not_a_json_object_is_refused(
    tmp_path: Path, text: str
) -> None:
    """T10."""
    _detector(tmp_path, "zz_stub")
    _pair(tmp_path, "zz_stub", manifest=text or " ")

    result = _run_root(tmp_path)

    assert _tokens(tmp_path) == {"zz_stub": "refused:manifest"}
    assert result.returncode == 1


def test_a_manifest_that_exists_and_cannot_be_read_is_refused_not_unbound(
    tmp_path: Path,
) -> None:
    """A directory where the manifest should be: reading it raises OSError."""
    _detector(tmp_path, "zz_stub")
    (tmp_path / "fixtures" / "zz_stub" / "fixture-pair.json").mkdir(parents=True)

    assert _tokens(tmp_path) == {"zz_stub": "refused:manifest"}


def test_unbound_is_decided_before_any_refusal(tmp_path: Path) -> None:
    """The verdict table is read in order: half a pair wins over a bad key."""
    _detector(tmp_path, "zz_stub")
    _pair(tmp_path, "zz_stub", _manifest(fixture_marker="fixture"), drop=("negative",))

    assert _tokens(tmp_path) == {"zz_stub": "unbound"}


# ---------------------------------------------------------------------------
# Outcomes of a run and the exit status
# ---------------------------------------------------------------------------


def test_a_directory_with_no_detectors_is_empty_and_never_clean(
    tmp_path: Path,
) -> None:
    """T13, first half."""
    result = _run_root(tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith("empty:fixture-binding - ")
    assert "clean" not in result.stdout
    assert binding_check.check_bindings(tmp_path).outcome == "empty"


def test_a_root_that_does_not_exist_is_unchecked_and_exits_two(
    tmp_path: Path,
) -> None:
    """T13, second half: a mistyped --root must not pass."""
    absent = tmp_path / "zz-absent"

    result = _run_root(absent)
    read = binding_check.check_bindings(absent)

    assert result.returncode == 2
    assert result.stdout.startswith("unchecked:fixture-binding - ")
    assert "clean" not in result.stdout
    assert "empty" not in result.stdout
    assert read.outcome == "unchecked"
    assert read.detectors == ()
    assert binding_check.detector_files(absent) is None


def test_a_root_that_is_a_file_is_unchecked(tmp_path: Path) -> None:
    target = tmp_path / "zz-file"
    target.write_text("zz\n", encoding="utf-8")

    assert _run_root(target).returncode == 2
    assert binding_check.check_bindings(target).outcome == "unchecked"


def test_a_directory_that_cannot_be_listed_is_unchecked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(self: Path):
        raise PermissionError("zz-denied")

    _detector(tmp_path, "zz_stub")
    monkeypatch.setattr(Path, "iterdir", refuse)

    read = binding_check.check_bindings(tmp_path)

    assert read.outcome == "unchecked"
    assert read.detectors == ()
    assert binding_check.exit_status(read) == 2
    assert binding_check.detector_files(tmp_path) is None


def test_the_exit_status_does_not_depend_on_what_reached_the_screen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T15: T1's input, with the printing taken away and then made to fail."""
    _detector(tmp_path, "zz_stub")

    monkeypatch.setattr("builtins.print", lambda *a, **k: None)
    assert binding_check.main(["--root", str(tmp_path)]) == 1

    def broken(*args: object, **kwargs: object) -> None:
        raise OSError("zz-closed")

    monkeypatch.setattr("builtins.print", broken)
    assert binding_check.main(["--root", str(tmp_path)]) != 0


def test_a_failure_inside_the_check_is_could_not_check_not_a_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def crash(root: Path):
        raise RuntimeError("zz-crash")

    monkeypatch.setattr(binding_check, "check_bindings", crash)

    assert binding_check.main(["--root", str(tmp_path)]) == 2
    out = capsys.readouterr().out
    assert out.startswith("unchecked:fixture-binding - ")
    assert "finding:" not in out


def _mixed_tree(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    root.mkdir()
    if name in ("functional", "mixed"):
        _detector(root, "zz_good")
        _pair(root, "zz_good")
    if name in ("unbound", "mixed"):
        _detector(root, "zz_unbound")
    if name in ("crash", "mixed"):
        _detector(root, "zz_crash", _always(2))
        _pair(root, "zz_crash")
    return root


@pytest.mark.parametrize(
    "name", ["empty", "functional", "unbound", "crash", "mixed", "absent"]
)
def test_exit_one_if_and_only_if_a_finding_line_was_printed(
    tmp_path: Path, name: str
) -> None:
    root = tmp_path / name if name == "absent" else _mixed_tree(tmp_path, name)

    result = _run_root(root)

    assert (result.returncode == 1) == bool(_findings(result.stdout))
    assert result.returncode in (0, 1, 2)
    assert result.stderr == ""


@pytest.mark.parametrize("name", ["empty", "functional", "unbound", "crash", "mixed"])
def test_the_last_line_says_what_the_check_left_out(tmp_path: Path, name: str) -> None:
    last = _run_root(_mixed_tree(tmp_path, name)).stdout.splitlines()[-1]

    assert "does not read the Constraint registry" in last
    assert "does not inspect fixture content" in last
    assert f"{_CHECK.name}" in last


def test_a_wrong_command_line_exits_two(tmp_path: Path) -> None:
    assert _run("--zz-unknown").returncode == 2
    assert _run("--format", "json").returncode == 2


def test_a_name_holding_a_line_break_cannot_forge_an_output_line(
    tmp_path: Path,
) -> None:
    _detector(tmp_path, "zz_stub")
    _pair(
        tmp_path,
        "zz_stub",
        manifest=_manifest(
            exemptions={"zz\nclean:fixture-binding - forged": "quoted.txt"}
        ),
        files={
            "positive.txt": f"{FLAG}\n",
            "negative.txt": "zz-quiet\n",
            "quoted.txt": f"{FLAG}\n",
        },
    )
    _detector(tmp_path, "zz\nclean:fixture-binding - forged")

    result = _run_root(tmp_path)

    assert result.returncode == 1
    assert len(_findings(result.stdout)) == 2
    assert not any(line.startswith("clean:") for line in result.stdout.splitlines())


def test_each_entry_carries_the_detector_file_name(tmp_path: Path) -> None:
    _detector(tmp_path, "zz_stub")

    _, entry = _one(tmp_path)

    assert (entry.name, entry.file_name) == ("zz_stub", "zz_stub.py")


def test_detector_files_lists_what_check_bindings_reports(tmp_path: Path) -> None:
    _detector(tmp_path, "zz_b")
    _detector(tmp_path, "zz_a")
    _detector(tmp_path, "zz_broken", "def broken(:\n")
    _detector(tmp_path, "zz_module", "ZZ_VALUE = 1\n")

    files = binding_check.detector_files(tmp_path)

    assert files == ("zz_a.py", "zz_b.py", "zz_broken.py")
    assert files == tuple(
        d.file_name for d in binding_check.check_bindings(tmp_path).detectors
    )


def test_undecided_files_names_the_listed_files_that_could_not_be_parsed(
    tmp_path: Path,
) -> None:
    _detector(tmp_path, "zz_a")
    _detector(tmp_path, "zz_broken", "def broken(:\n")
    _detector(tmp_path, "zz_text", "TODO: write this detector later\n")
    _detector(tmp_path, "zz_module", "ZZ_VALUE = 1\n")

    undecided = binding_check.undecided_files(tmp_path)

    assert undecided == ("zz_broken.py", "zz_text.py")
    assert binding_check.detector_files(tmp_path) == (
        "zz_a.py",
        "zz_broken.py",
        "zz_text.py",
    )


def test_undecided_files_names_a_listed_file_that_could_not_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _detector(tmp_path, "zz_a")
    _detector(tmp_path, "zz_noread")
    read_bytes = Path.read_bytes

    def refuse(self: Path) -> bytes:
        if self.name == "zz_noread.py":
            raise PermissionError("zz-refused")
        return read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", refuse)

    assert binding_check.undecided_files(tmp_path) == ("zz_noread.py",)


def test_undecided_files_is_empty_when_every_file_parses_and_none_without_a_directory(
    tmp_path: Path,
) -> None:
    _detector(tmp_path / "zz_dir", "zz_a")
    _detector(tmp_path / "zz_dir", "zz_module", "ZZ_VALUE = 1\n")

    assert binding_check.undecided_files(tmp_path / "zz_dir") == ()
    assert binding_check.undecided_files(tmp_path / "zz_absent") is None


# ---------------------------------------------------------------------------
# The tree the product ships
# ---------------------------------------------------------------------------


def _shipped_manifests() -> list[Path]:
    return sorted(_SHIPPED_FIXTURES.glob("*/fixture-pair.json"))


@pytest.mark.process
def test_shipped_detectors_are_each_proven_by_their_pair() -> None:
    """T16: the check, with no arguments, against the shipped tree."""
    result = _run()
    read = binding_check.check_bindings(_DETECTORS_DIR)

    assert result.returncode == 0
    assert result.stderr == ""
    assert _findings(result.stdout) == []
    assert "detector: orphan_check.py: functional" in result.stdout.splitlines()
    assert result.stdout.splitlines()[-1].startswith("clean:fixture-binding - ")
    assert {d.name: d.token for d in read.detectors} == {"orphan_check": "functional"}
    assert not any(
        line.startswith(("finding:", "detector:")) and _CHECK.name in line
        for line in result.stdout.splitlines()
    )


@pytest.mark.process
def test_every_shipped_pair_declares_both_standing_exemptions() -> None:
    """T17."""
    manifests = _shipped_manifests()
    assert manifests, "no shipped pair was found, so nothing was checked"

    for path in manifests:
        declared = json.loads(path.read_text(encoding="utf-8"))["exemptions"]
        missing = [name for name in STANDING_EXEMPTIONS if name not in declared]
        assert not missing, f"{path.parent.name} does not declare {missing}"

    shipped = {path.parent.name for path in manifests}
    detectors = {
        Path(name).stem for name in binding_check.detector_files(_DETECTORS_DIR)
    }
    assert detectors <= shipped


def _live_names() -> dict[str, set[str]]:
    """Names this repository uses for real things, derived from its tree."""
    skills = {
        entry.name
        for parent in (
            _POV / "skills",
            _POV.parent / "skills",
            _ROOT / ".claude/skills",
        )
        for entry in parent.iterdir()
        if entry.is_dir()
    }
    agents = {
        entry.stem
        for parent in (
            _POV / "agents",
            _POV.parent / "agents",
            _ROOT / ".claude/agents",
        )
        for entry in parent.iterdir()
    }
    constraints = {
        match.group(0)
        for path in (_POV / "constraints").rglob("*.md")
        if (match := re.match(r"[A-Z]+-\d+[a-z]?(?=-)", path.name))
    }
    return {"skill": skills, "agent": agents, "constraint": constraints}


def _live_names_in(text: str, names: set[str]) -> list[str]:
    return sorted(
        name
        for name in names
        if re.search(
            rf"(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])", text, re.I
        )
    )


def test_the_live_name_search_finds_a_live_name() -> None:
    """Positive control for the test below."""
    names = _live_names()

    assert all(names.values()), {kind: len(found) for kind, found in names.items()}
    for kind, found in names.items():
        sample = sorted(found)[0]
        assert _live_names_in(f"ZZ-01,{sample},\n", found) == [sample], kind
    assert _live_names_in("ZZ-01,checks/zz01.py,\n", set().union(*names.values())) == []


@pytest.mark.process
def test_shipped_fixtures_use_synthetic_identifiers_only() -> None:
    """T18."""
    names = set().union(*_live_names().values())
    files = [path for path in _SHIPPED_FIXTURES.rglob("*") if path.is_file()]
    assert files, "no shipped fixture file was found, so nothing was checked"

    for path in files:
        found = _live_names_in(path.read_text(encoding="utf-8"), names)
        assert not found, (
            f"{path.relative_to(_ROOT)} names {found}. A fixture uses synthetic "
            "identifiers only. Checked against skill directory names, agent names "
            "and Constraint ids derived from this repository; module names are "
            "not checked."
        )


@pytest.mark.process
def test_no_fixture_pair_is_declared_outside_the_fixture_location() -> None:
    """T19."""
    manifests = sorted(_POV.rglob("fixture-pair.json"))
    assert manifests, "no manifest was found, so nothing was checked"

    stray = [
        str(path.relative_to(_ROOT))
        for path in manifests
        if path.parent.parent != _SHIPPED_FIXTURES
    ]
    assert stray == []


@pytest.mark.process
def test_the_shipped_exemption_fixtures_are_what_their_ids_say() -> None:
    """The quotation is a quoted field; the historical record is a sibling."""
    pair = _SHIPPED_FIXTURES / "orphan_check"
    manifest = json.loads((pair / "fixture-pair.json").read_text(encoding="utf-8"))
    quotation = pair / manifest["exemptions"]["labelled-evidentiary-quotation"]
    historical = pair / manifest["exemptions"]["historical-record-not-to-inherit"]

    # Read as lines, the quotation holds a row with no Detector and no marking.
    assert any(
        re.fullmatch(r"ZZ-\d+,,", line)
        for line in quotation.read_text(encoding="utf-8").splitlines()
    )
    assert historical.parent != pair
    beside = [path for path in historical.parent.iterdir() if path != historical]
    assert beside
    for path in beside:
        flagged = subprocess.run(
            [
                sys.executable,
                "-B",
                str(_DETECTORS_DIR / "orphan_check.py"),
                "--registry",
                str(path),
            ],
            capture_output=True,
            text=True,
        )
        assert flagged.returncode == 1, path.name

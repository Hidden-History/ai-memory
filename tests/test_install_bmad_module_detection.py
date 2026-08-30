"""Install tests for Module-granularity BMAD detection (Story 1.5, AD-33).

The installer reports whether the BMAD **BMM Module** is available to the target
project, at Module granularity, and never changes the install's exit status for it.

Three states, and they are three — not "present/absent":

  * ``bmad-absent``  — no BMAD root under the project path                  (AC-1)
  * ``bmm-absent``   — BMAD root present, the BMM Module is not             (AC-2)
  * ``bmm-present``  — the BMM Module is installed                          (AC-3)

Two surfaces are covered:

  1. ``detect_bmad_module_state()`` — resolves exactly one of the three states and
     writes it to stdout. It emits no operator-facing output, so state resolution
     is assertable without capturing a message.
  2. ``report_bmad_module_state()`` — maps a state to the operator-facing line.
     Absence is reported; presence is silent on a normal run (AC-3).

**AC-4 is asserted against the declared design.** ``install.sh`` implements
*design A* of the two the story allows: one function, state on stdout,
``return 0`` always. For design A the AC-4 guarantee lives in the function's
**return discipline**, not in the call-site shape — a call site is an assignment
by construction there, so asserting its shape would prove nothing. These tests
therefore assert the return status directly, in every state including unreadable
evidence, and additionally assert the call site is not a bare consumption.

Harness: the repo's ``install_sh_no_main`` fixture, copied into this module as a
per-module fixture exactly as the other install-test modules do (it is not a
``conftest.py`` fixture and is not imported across modules). It copies the real
``install.sh`` minus its final ``main "$@"`` line and sources that copy, so the
real function bodies execute. A full ``bash install.sh`` subprocess would require
performing a real install to reach these functions, and no live system is
touched by this suite.

Declared exemption set (AD-20a) — trees the detector must **not** report as
``bmm-absent``:

  * ``EXEMPT_SIBLING_OUTPUT_TREE`` — a project carrying a similarly-named output
    tree (``_bmad-output/``) but no BMAD root. This is not a near-miss in theory:
    the repository this installer ships from carries exactly that directory.
  * ``EXEMPT_NESTED_BMAD_ROOT`` — a BMAD root that exists only deeper in the
    tree (``vendor/_bmad/``). Detection resolves relative to the project path it
    is given (N-8), so a nested root belongs to a different project.
  * ``EXEMPT_MODULE_INSTALLED`` — a project with the BMM Module installed. The
    positive direction of the pair: the state the detector must not mistake for
    the defect it reports.

Synthetic identifiers throughout. The one live name used is the literal ``bmm``,
which is the Module under test and is named by the requirement itself.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"

# AD-20a declared exemption set — see module docstring.
EXEMPT_SIBLING_OUTPUT_TREE = "_bmad-output"
EXEMPT_NESTED_BMAD_ROOT = "vendor/_bmad"
EXEMPT_MODULE_INSTALLED = "_bmad/bmm/config.yaml"

STATE_BMAD_ABSENT = "bmad-absent"
STATE_BMM_ABSENT = "bmm-absent"
STATE_BMM_PRESENT = "bmm-present"


@pytest.fixture
def install_sh_no_main(tmp_path) -> Path:
    """Copy install.sh minus final 'main "$@"' line into tmp_path for safe sourcing."""
    content = _INSTALL_SH.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    assert lines[-1].strip() == 'main "$@"', (
        f"Expected last line 'main \"$@\"', got: {lines[-1]!r}. "
        "If install.sh structure changed, update this fixture."
    )
    copy = tmp_path / "install.sh"
    copy.write_text("".join(lines[:-1]), encoding="utf-8")
    copy.chmod(0o755)
    shutil.copy(
        _SCRIPTS_DIR / "_env_split_helpers.sh", tmp_path / "_env_split_helpers.sh"
    )
    return copy


def _project(tmp_path, name: str, *relative_dirs: str) -> Path:
    """Build a synthetic project tree, creating each relative directory under it."""
    project = tmp_path / name
    project.mkdir()
    for relative in relative_dirs:
        (project / relative).mkdir(parents=True)
    return project


def _module_config(project: Path) -> Path:
    """Write the BMM Module's own config — the discriminator the detector reads."""
    config = project / "_bmad" / "bmm" / "config.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("module_name: sample-module\n", encoding="utf-8")
    return config


def _detect(install_sh_copy: Path, project: Path) -> subprocess.CompletedProcess:
    """Source install.sh and resolve the state for `project`, reporting the status.

    Runs under the same `set -euo pipefail` the real script runs under, and echoes
    the detector's return status on a trailing line so AC-4 can be asserted
    directly rather than inferred from the call site. The capture is a plain
    assignment, never `local`/`declare` — a declaration command's exit status is
    its own, which would swallow the very non-zero return AC-4 exists to catch.
    """
    bash_cmd = f"""
set -euo pipefail
source "{install_sh_copy}"
state=$(detect_bmad_module_state "{project}")
rc=$?
echo "STATE=$state"
echo "RC=$rc"
echo "REACHED_END=yes"
"""
    return subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)


def _state_of(result: subprocess.CompletedProcess) -> str:
    for line in result.stdout.splitlines():
        if line.startswith("STATE="):
            return line[len("STATE=") :].strip()
    raise AssertionError(
        f"No STATE= line in detector output.\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def _report(
    install_sh_copy: Path, project: Path, out_file: Path
) -> subprocess.CompletedProcess:
    """Run the reporter with its whole output isolated into `out_file`.

    Sourcing the script emits nothing today, but AC-3's assertion is about what
    the reporting call emits, so the call's own streams are captured separately
    rather than diffed out of the surrounding run.
    """
    bash_cmd = f"""
set -euo pipefail
source "{install_sh_copy}"
report_bmad_module_state "{project}" > "{out_file}" 2>&1
echo "REACHED_END=yes"
"""
    return subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)


@pytest.fixture
def unreadable_bmad_root(tmp_path):
    """A BMAD root that exists but cannot be traversed, restored on teardown.

    Skipped when the running user can traverse it regardless of mode (root, or a
    filesystem that does not enforce POSIX permissions) — otherwise the test
    would assert nothing while appearing to pass.
    """
    project = _project(tmp_path, "unreadable_project")
    root = project / "_bmad"
    root.mkdir()
    (root / "bmm").mkdir()
    root.chmod(0o000)
    try:
        still_readable = (root / "bmm").is_dir()
    except PermissionError:
        still_readable = False
    if still_readable:
        root.chmod(0o755)
        pytest.skip("filesystem or user does not enforce directory permissions")
    yield project
    root.chmod(0o755)


class TestDetectorResolvesThreeStates:
    """AC-1, AC-2, AC-3 — three distinct states, not present/absent."""

    def test_no_bmad_at_all_resolves_bmad_absent(self, install_sh_no_main, tmp_path):
        """AC-1: a repository with no BMAD at all resolves the named absent state."""
        project = _project(tmp_path, "no_bmad_project", "docs")

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMAD_ABSENT

    def test_bmad_root_without_module_resolves_bmm_absent(
        self, install_sh_no_main, tmp_path
    ):
        """AC-2: BMAD present, BMM absent is its own state — the middle one."""
        project = _project(
            tmp_path,
            "partial_bmad_project",
            "_bmad/sample-module-one",
            "_bmad/sample-module-two",
        )
        (project / "_bmad" / "config.yaml").write_text(
            "sample-module-one:\n  name: Sample Module One\n", encoding="utf-8"
        )

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMM_ABSENT

    def test_empty_module_directory_is_not_an_installed_module(
        self, install_sh_no_main, tmp_path
    ):
        """AC-2: the Module claim is made on the Module's own config, not a bare dir."""
        project = _project(tmp_path, "empty_module_project", "_bmad/bmm")

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMM_ABSENT

    def test_module_config_present_resolves_bmm_present(
        self, install_sh_no_main, tmp_path
    ):
        """AC-3: the Module's own config is the evidence for BMM present."""
        project = _project(tmp_path, "full_bmad_project")
        _module_config(project)

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMM_PRESENT

    def test_root_config_naming_other_modules_does_not_decide_bmm(
        self, install_sh_no_main, tmp_path
    ):
        """The BMAD root config is not a module registry — reading it inverts AC-2.

        A root config naming only other modules, on a tree that *has* BMM, must
        still resolve `bmm-present`. A detector that parsed the root config would
        report the Module dark on a machine where it is lit.
        """
        project = _project(tmp_path, "root_config_project")
        _module_config(project)
        (project / "_bmad" / "config.yaml").write_text(
            "sample-module-one:\n  name: Sample Module One\n", encoding="utf-8"
        )

        result = _detect(install_sh_no_main, project)

        assert _state_of(result) == STATE_BMM_PRESENT


class TestReportedMessages:
    """AC-1, AC-2, AC-3 — what the operator actually sees in each state."""

    def test_bmad_absent_is_a_named_report_not_a_silence(
        self, install_sh_no_main, tmp_path
    ):
        """AC-1: absence is a named state. Reporting nothing does not satisfy it."""
        project = _project(tmp_path, "no_bmad_project")
        out_file = tmp_path / "out-absent.txt"

        result = _report(install_sh_no_main, project, out_file)
        output = out_file.read_text(encoding="utf-8")

        assert result.returncode == 0, result.stderr
        assert "BMAD absent" in output, output

    def test_bmm_absent_message_names_bmm_as_the_required_module(
        self, install_sh_no_main, tmp_path
    ):
        """AC-2: the message names BMM. "BMAD is incomplete" does not satisfy it."""
        project = _project(tmp_path, "partial_bmad_project", "_bmad/sample-module-one")
        out_file = tmp_path / "out-bmm-absent.txt"

        result = _report(install_sh_no_main, project, out_file)
        output = out_file.read_text(encoding="utf-8")

        assert result.returncode == 0, result.stderr
        assert "BMM" in output, output
        assert "Module" in output, output

    def test_bmm_absent_message_is_distinguishable_from_bmad_absent(
        self, install_sh_no_main, tmp_path
    ):
        """AC-2: told "BMAD absent" on a machine with most of BMAD is the defect."""
        partial = _project(tmp_path, "partial_project", "_bmad/sample-module-one")
        absent = _project(tmp_path, "absent_project")
        partial_out = tmp_path / "partial.txt"
        absent_out = tmp_path / "absent.txt"

        _report(install_sh_no_main, partial, partial_out)
        _report(install_sh_no_main, absent, absent_out)

        partial_text = partial_out.read_text(encoding="utf-8")
        absent_text = absent_out.read_text(encoding="utf-8")
        assert partial_text != absent_text
        assert "BMAD absent" not in partial_text, partial_text

    def test_bmm_present_emits_nothing_at_all(self, install_sh_no_main, tmp_path):
        """AC-3: silence is the required behaviour — a reassuring line is a defect.

        Asserts the absence of *output*, not the absence of the word "warning".
        """
        project = _project(tmp_path, "full_bmad_project")
        _module_config(project)
        out_file = tmp_path / "out-present.txt"

        result = _report(install_sh_no_main, project, out_file)
        output = out_file.read_text(encoding="utf-8")

        assert result.returncode == 0, result.stderr
        assert output == "", f"expected silence when BMM is present, got: {output!r}"

    def test_absence_messages_carry_no_version_and_no_upstream_source(
        self, install_sh_no_main, tmp_path
    ):
        """Scope boundary: the route out is Story 1.6's, and AD-1/AD-2 forbid it here."""
        project = _project(tmp_path, "partial_bmad_project", "_bmad/sample-module-one")
        out_file = tmp_path / "out.txt"

        _report(install_sh_no_main, project, out_file)
        output = out_file.read_text(encoding="utf-8")

        # Non-vacuity: an empty file satisfies every "not in" below, so assert
        # there is a message to inspect before inspecting it.
        assert "BMM" in output, output
        assert "http" not in output.lower(), output
        assert "github" not in output.lower(), output
        assert not re.search(r"\bv?\d+\.\d+", output), output


class TestNeverAbortsTheInstall:
    """AC-4 — the detection path cannot change the installer's exit status."""

    @pytest.mark.parametrize(
        "dirs,write_config",
        [
            ((), False),
            (("_bmad/sample-module-one",), False),
            ((), True),
        ],
        ids=["bmad-absent", "bmm-absent", "bmm-present"],
    )
    def test_detector_returns_zero_in_every_state(
        self, install_sh_no_main, tmp_path, dirs, write_config
    ):
        """AC-4: design A carries its guarantee in the return status. Assert it."""
        project = _project(tmp_path, "project", *dirs)
        if write_config:
            _module_config(project)

        result = _detect(install_sh_no_main, project)

        assert "RC=0" in result.stdout, result.stdout
        assert "REACHED_END=yes" in result.stdout, result.stdout
        assert result.returncode == 0, result.stderr

    def test_detector_returns_zero_when_evidence_is_unreadable(
        self, install_sh_no_main, unreadable_bmad_root
    ):
        """AC-4: an internal step returning non-zero must not escape under errexit.

        An unreadable BMAD root makes the Module test fail rather than answer.
        What the detector *reports* in that case is an open spine question
        (AD-24: an unclassified condition is a spine defect, not an
        implementer's judgement call) and is deliberately not asserted here.
        What is asserted is the whole of AC-4: the run survives it.
        """
        result = _detect(install_sh_no_main, unreadable_bmad_root)

        assert "RC=0" in result.stdout, result.stdout
        assert "REACHED_END=yes" in result.stdout, result.stdout
        assert result.returncode == 0, result.stderr

    def test_reporter_survives_unreadable_evidence(
        self, install_sh_no_main, unreadable_bmad_root, tmp_path
    ):
        """AC-4: the reporting half of the path is subject to the same rule."""
        out_file = tmp_path / "out-unreadable.txt"

        result = _report(install_sh_no_main, unreadable_bmad_root, out_file)

        assert "REACHED_END=yes" in result.stdout, result.stdout
        assert result.returncode == 0, result.stderr

    def test_detector_returns_zero_for_a_nonexistent_project_path(
        self, install_sh_no_main, tmp_path
    ):
        """AC-4: a path that is not there is still not an abort."""
        result = _detect(install_sh_no_main, tmp_path / "no_such_project")

        assert "RC=0" in result.stdout, result.stdout
        assert result.returncode == 0, result.stderr

    def test_call_site_in_main_is_not_a_bare_consumption(self):
        """AC-4 / Anti-pattern 7: a bare call under `set -e` aborts the install.

        Design A already returns 0 unconditionally, so this is the second of two
        independent guarantees rather than the only one.
        """
        source = _INSTALL_SH.read_text(encoding="utf-8")
        call_lines = [
            line.strip()
            for line in source.splitlines()
            if "report_bmad_module_state" in line
            and not line.strip().startswith("#")
            and "report_bmad_module_state()" not in line
        ]

        assert (
            call_lines
        ), "no call site for report_bmad_module_state found in install.sh"
        for line in call_lines:
            assert line.startswith("if ") or "||" in line, (
                f"bare call site under `set -euo pipefail`: {line!r}. "
                "Consume it in a condition."
            )

    def test_install_sh_still_runs_under_errexit(self):
        """The premise AC-4 rests on — asserted, not assumed."""
        source = _INSTALL_SH.read_text(encoding="utf-8")

        assert "\nset -euo pipefail\n" in source


class TestDeclaredExemptions:
    """AD-20a — the fixture pair, both directions.

    One tree the detector must flag as `bmm-absent`, and one tree per declared
    exemption it must not flag.
    """

    def test_flags_the_defect_it_reports(self, install_sh_no_main, tmp_path):
        """The fixture that must fail on the defect: BMAD root, no Module."""
        project = _project(tmp_path, "defect_project", "_bmad/sample-module-one")

        assert _state_of(_detect(install_sh_no_main, project)) == STATE_BMM_ABSENT

    def test_exempt_sibling_output_tree_is_not_a_bmad_root(
        self, install_sh_no_main, tmp_path
    ):
        """`_bmad-output/` is a similarly-named output tree, not a BMAD root."""
        project = _project(tmp_path, "output_tree_project", EXEMPT_SIBLING_OUTPUT_TREE)

        state = _state_of(_detect(install_sh_no_main, project))

        assert (
            state == STATE_BMAD_ABSENT
        ), f"detector fired on declared exemption {EXEMPT_SIBLING_OUTPUT_TREE!r}"

    def test_exempt_nested_bmad_root_belongs_to_another_project(
        self, install_sh_no_main, tmp_path
    ):
        """Detection resolves beneath the project path it is given (N-8)."""
        project = _project(tmp_path, "nested_project", EXEMPT_NESTED_BMAD_ROOT)

        state = _state_of(_detect(install_sh_no_main, project))

        assert (
            state == STATE_BMAD_ABSENT
        ), f"detector fired on declared exemption {EXEMPT_NESTED_BMAD_ROOT!r}"

    def test_exempt_module_installed_is_never_reported_as_missing(
        self, install_sh_no_main, tmp_path
    ):
        """The positive direction: an installed Module is not the defect."""
        project = _project(tmp_path, "installed_project")
        _module_config(project)

        state = _state_of(_detect(install_sh_no_main, project))

        assert (
            state == STATE_BMM_PRESENT
        ), f"detector fired on declared exemption {EXEMPT_MODULE_INSTALLED!r}"


class TestDetectionIsNotPersisted:
    """AD-26 — installing the dependency later must not require a reinstall."""

    def test_detector_writes_nothing_into_the_project(
        self, install_sh_no_main, tmp_path
    ):
        """Nothing about the degraded state may be cached into a durable artifact."""
        project = _project(tmp_path, "no_bmad_project", "docs")
        before = sorted(p.relative_to(project) for p in project.rglob("*"))

        result = _detect(install_sh_no_main, project)
        out_file = tmp_path / "out.txt"
        _report(install_sh_no_main, project, out_file)

        # Non-vacuity: a detector that never ran also writes nothing. Assert it ran.
        assert _state_of(result) == STATE_BMAD_ABSENT
        assert out_file.read_text(encoding="utf-8").strip()

        after = sorted(p.relative_to(project) for p in project.rglob("*"))
        assert before == after

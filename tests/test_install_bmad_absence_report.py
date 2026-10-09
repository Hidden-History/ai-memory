"""Install tests for the BMAD absence report and the project-path stop.

Two installer behaviours are covered, both by sourcing a copy of `install.sh`
with its final `main "$@"` line removed — the installer itself is never run:

  1. ``report_bmad_absence`` — when BMAD or its required Module is not available
     to the target project, the installer lists each unavailable capability on
     its own line and gives the route out: the upstream source and the expected
     version scope. It prints nothing when the Module is present, and it never
     changes the install's exit status.
  2. The project-path argument — a target the installer cannot enter stops the
     run with an error naming it, instead of silently using the current
     directory.

The copy sits in a synthetic product tree, so the declarations the report reads
are fixtures with synthetic identifiers, not the shipped ones.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).parent.parent
_SCRIPTS_DIR = _REPO / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"
_POV = "_ai-memory/pov"

ROOT_CAPABILITY = "cap:sample-needs-root"
MODULE_CAPABILITY = "cap:sample-needs-module"
SAMPLE_SOURCE = "https://example.invalid/sample-upstream"
SAMPLE_SCOPE = "sample-scope-one"

# The same curated PATH the detection tests use, plus `python3`, which the
# report runs. Nothing else resolves — `docker` above all.
_HARNESS_TOOLS = ("bash", "basename", "dirname", "sed", "tr", "python3")

_harness = {}


@pytest.fixture(scope="module", autouse=True)
def _harness_sandbox(tmp_path_factory):
    root = tmp_path_factory.mktemp("absence-harness")
    for name, tools in (
        ("bin", _HARNESS_TOOLS),
        ("bin-no-python", _HARNESS_TOOLS[:-1]),
    ):
        bin_dir = root / name
        bin_dir.mkdir()
        for tool in tools:
            real = shutil.which(tool, path="/usr/bin:/bin")
            if real is None:
                pytest.fail(f"harness tool {tool!r} not found in /usr/bin or /bin")
            (bin_dir / tool).symlink_to(real)
    home = root / "home"
    home.mkdir()
    _harness.update(
        path=str(root / "bin"), no_python=str(root / "bin-no-python"), home=str(home)
    )
    yield
    _harness.clear()


def _env(python: bool = True, log_level: str = "info") -> dict:
    """Built, never inherited: no install binding, no credentials, no docker."""
    assert _harness, "harness sandbox not set up"
    return {
        "PATH": _harness["path"] if python else _harness["no_python"],
        "HOME": _harness["home"],
        "LOG_LEVEL": log_level,
    }


def _block(marker: str, **fields: str) -> str:
    body = "".join(f"{key}: {value}\n" for key, value in fields.items())
    return f"<!-- ai-memory:{marker}\n{body}ai-memory:end-{marker} -->\n"


@pytest.fixture
def product(tmp_path) -> Path:
    """A synthetic product tree holding a no-`main` copy of the installer."""
    root = tmp_path / "product"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    lines = _INSTALL_SH.read_text(encoding="utf-8").splitlines(keepends=True)
    assert lines[-1].strip() == 'main "$@"', lines[-1]
    (scripts / "install.sh").write_text("".join(lines[:-1]), encoding="utf-8")
    for name in ("_env_split_helpers.sh", "bmad_absence_report.py"):
        if (_SCRIPTS_DIR / name).is_file():
            shutil.copy(_SCRIPTS_DIR / name, scripts / name)
    (root / "src" / "memory").mkdir(parents=True)
    shutil.copy(_REPO / "src" / "memory" / "degraded.py", root / "src" / "memory")

    for name, capability, member in (
        ("sample-one", ROOT_CAPABILITY, "bmad"),
        ("sample-two", MODULE_CAPABILITY, "bmad.bmm"),
    ):
        site = root / _POV / "skills" / name / "SKILL.md"
        site.parent.mkdir(parents=True)
        site.write_text(
            _block(
                "degraded-declaration",
                capability=capability,
                depends_on=member,
                degraded_behaviour="reports itself unavailable",
                degraded_test="not-yet-enforced",
            ),
            encoding="utf-8",
        )
    (root / _POV / "DEPENDENCIES.md").write_text(
        _block(
            "dependency-declaration", dependency="bmad", upstream_source=SAMPLE_SOURCE
        ),
        encoding="utf-8",
    )
    (root / _POV / "BMAD-PIN.md").write_text(
        _block(
            "pin-declaration",
            dependency="bmad",
            version_scope=SAMPLE_SCOPE,
            covers="bmad.bmm",
        ),
        encoding="utf-8",
    )
    return root


def _project(tmp_path, *relative: str) -> Path:
    project = tmp_path / "sample-project"
    project.mkdir(parents=True)
    for part in relative:
        target = project / part
        target.parent.mkdir(parents=True, exist_ok=True)
        if part.endswith(".yaml"):
            target.write_text("module_name: sample-module\n", encoding="utf-8")
        else:
            target.mkdir(exist_ok=True)
    return project


def _report(
    product: Path, project_arg: str, override: str = "", **env
) -> tuple[subprocess.CompletedProcess, str]:
    """Run the absence report with its own output isolated from the run's."""
    out_file = product / "report.out"
    bash_cmd = f"""
set -euo pipefail
source "{product}/scripts/install.sh"
{override}
report_bmad_absence "{project_arg}" > "{out_file}" 2>&1
echo "REACHED_END=yes"
"""
    result = subprocess.run(
        ["bash", "-c", bash_cmd], capture_output=True, text=True, env=_env(**env)
    )
    return result, out_file.read_text(encoding="utf-8") if out_file.exists() else ""


def _lines_naming(output: str, token: str) -> list:
    return [line for line in output.splitlines() if token in line]


class TestFiringStates:
    def test_no_bmad_lists_every_capability_on_its_own_line(self, product, tmp_path):
        result, output = _report(product, str(_project(tmp_path)))
        assert "REACHED_END=yes" in result.stdout, result.stderr
        for capability in (ROOT_CAPABILITY, MODULE_CAPABILITY):
            lines = _lines_naming(output, capability)
            assert len(lines) == 1, output
            assert "unsatisfied" in lines[0]
        assert not _lines_naming(output, ROOT_CAPABILITY)[0].count(MODULE_CAPABILITY)

    def test_module_absent_lists_only_the_capability_that_needs_the_module(
        self, product, tmp_path
    ):
        _, output = _report(product, str(_project(tmp_path, "_bmad")))
        assert len(_lines_naming(output, MODULE_CAPABILITY)) == 1
        assert _lines_naming(output, ROOT_CAPABILITY) == []

    def test_undetermined_evidence_lists_capabilities_with_that_cause(self, product):
        # An empty project path is the detector's own indeterminate case, and it
        # needs no permission fixture.
        result, output = _report(product, "")
        assert "REACHED_END=yes" in result.stdout, result.stderr
        for capability in (ROOT_CAPABILITY, MODULE_CAPABILITY):
            lines = _lines_naming(output, capability)
            assert len(lines) == 1, output
            assert "indeterminate" in lines[0]
            assert "unsatisfied" not in lines[0]

    @pytest.mark.parametrize("layout", [(), ("_bmad",)])
    def test_route_out_carries_the_source_and_the_pins_version_scope(
        self, product, tmp_path, layout
    ):
        _, output = _report(product, str(_project(tmp_path, *layout)))
        assert len(_lines_naming(output, SAMPLE_SOURCE)) == 1
        scope_lines = _lines_naming(output, SAMPLE_SCOPE)
        assert len(scope_lines) == 1
        assert "bmad.bmm" in scope_lines[0]

    def test_version_scope_follows_the_pin_file(self, product, tmp_path):
        pin = product / _POV / "BMAD-PIN.md"
        pin.write_text(
            pin.read_text(encoding="utf-8").replace(SAMPLE_SCOPE, "sample-scope-two"),
            encoding="utf-8",
        )
        _, output = _report(product, str(_project(tmp_path)))
        assert _lines_naming(output, "sample-scope-two")
        assert _lines_naming(output, SAMPLE_SCOPE) == []


class TestSilenceAndUnknownStates:
    @pytest.mark.parametrize("log_level", ["info", "debug"])
    def test_module_present_prints_nothing_at_all(self, product, tmp_path, log_level):
        project = _project(tmp_path, "_bmad/bmm/config.yaml")
        result, output = _report(product, str(project), log_level=log_level)
        assert "REACHED_END=yes" in result.stdout, result.stderr
        assert output == ""

    @pytest.mark.parametrize("token", ["sample-unrecognised", ""])
    def test_an_unrecognised_state_is_reported_and_is_not_an_enumeration(
        self, product, tmp_path, token
    ):
        override = f'detect_bmad_module_state() {{ echo "{token}"; }}'
        result, output = _report(product, str(_project(tmp_path)), override)
        assert "REACHED_END=yes" in result.stdout, result.stderr
        assert "state-unrecognised" in output
        assert _lines_naming(output, "cap:") == []

    def test_every_detector_state_has_exactly_one_outcome(self, product, tmp_path):
        outcomes = {}
        for token in (
            "bmad-absent",
            "bmm-absent",
            "bmad-indeterminate",
            "bmm-present",
            "sample-unrecognised",
        ):
            override = f'detect_bmad_module_state() {{ echo "{token}"; }}'
            _, output = _report(product, str(_project(tmp_path / token)), override)
            outcomes[token] = (
                "silent"
                if output == ""
                else "unrecognised" if "state-unrecognised" in output else "fires"
            )
        assert outcomes == {
            "bmad-absent": "fires",
            "bmm-absent": "fires",
            "bmad-indeterminate": "fires",
            "bmm-present": "silent",
            "sample-unrecognised": "unrecognised",
        }


class TestDistinguishableEmptyResults:
    def _only_root_capability(self, product):
        shutil.rmtree(product / _POV / "skills" / "sample-two")

    def test_nothing_dark_is_a_stated_empty_result_not_silence(self, product, tmp_path):
        self._only_root_capability(product)
        _, output = _report(product, str(_project(tmp_path, "_bmad")))
        assert "enumeration-empty" in output
        assert _lines_naming(output, "cap:") == []
        assert _lines_naming(output, SAMPLE_SOURCE)

    def test_discovery_that_did_not_run_is_stated_as_such(self, product, tmp_path):
        shutil.rmtree(product / "_ai-memory")
        _, output = _report(product, str(_project(tmp_path)))
        assert "enumeration-did-not-run" in output
        assert "enumeration-empty" not in output

    def test_discovery_that_failed_is_stated_as_such(self, product, tmp_path):
        broken = product / _POV / "skills" / "sample-broken" / "SKILL.md"
        broken.parent.mkdir()
        broken.write_text("<!-- ai-memory:degraded-declaration\n", encoding="utf-8")
        _, output = _report(product, str(_project(tmp_path)))
        assert "enumeration-failed" in output
        assert "enumeration-empty" not in output


class TestPinStatesReachTheOperator:
    def test_missing_pin_is_reported_and_the_rest_still_renders(
        self, product, tmp_path
    ):
        (product / _POV / "BMAD-PIN.md").unlink()
        _, output = _report(product, str(_project(tmp_path)))
        assert "pin-missing" in output
        assert _lines_naming(output, SAMPLE_SCOPE) == []
        assert len(_lines_naming(output, "cap:")) == 2
        assert _lines_naming(output, SAMPLE_SOURCE)

    def test_empty_pin_is_reported_differently_from_missing(self, product, tmp_path):
        (product / _POV / "BMAD-PIN.md").write_text("nothing here\n", encoding="utf-8")
        _, output = _report(product, str(_project(tmp_path)))
        assert "pin-empty" in output
        assert "pin-missing" not in output

    def test_unreadable_pin_is_reported_differently_again(self, product, tmp_path):
        pin = product / _POV / "BMAD-PIN.md"
        pin.unlink()
        pin.mkdir()
        _, output = _report(product, str(_project(tmp_path)))
        assert "pin-unreadable" in output
        assert "pin-missing" not in output


class TestTheReportCannotStopTheInstall:
    def test_a_report_that_cannot_run_is_reported_not_silent(self, product, tmp_path):
        (product / "scripts" / "bmad_absence_report.py").unlink()
        result, output = _report(product, str(_project(tmp_path)))
        assert "REACHED_END=yes" in result.stdout, result.stderr
        assert "report-could-not-run" in output
        assert "bmad_absence_report.py" in output

    def test_no_python_is_reported_not_silent(self, product, tmp_path):
        result, output = _report(product, str(_project(tmp_path)), python=False)
        assert "REACHED_END=yes" in result.stdout, result.stderr
        assert "report-could-not-run" in output

    def test_a_truncated_report_is_not_rendered_as_a_complete_one(
        self, product, tmp_path
    ):
        (product / "scripts" / "bmad_absence_report.py").write_text(
            f"print('capability\\t{ROOT_CAPABILITY}\\tunsatisfied')\n", encoding="utf-8"
        )
        _, output = _report(product, str(_project(tmp_path)))
        assert "report-could-not-run" in output

    def test_bare_call_returns_zero_under_errexit(self, product, tmp_path):
        (product / "scripts" / "bmad_absence_report.py").unlink()
        bash_cmd = f"""
set -euo pipefail
source "{product}/scripts/install.sh"
report_bmad_absence "{_project(tmp_path)}" > /dev/null 2>&1
echo "RC=$?"
"""
        result = subprocess.run(
            ["bash", "-c", bash_cmd], capture_output=True, text=True, env=_env()
        )
        assert "RC=0" in result.stdout, result.stderr


def _function_body(name: str) -> str:
    text = _INSTALL_SH.read_text(encoding="utf-8")
    match = re.search(rf"^{name}\(\) \{{\n(.*?)^\}}\n", text, re.S | re.M)
    assert match, f"{name}() not found in install.sh"
    return match.group(1)


def _code_lines(body: str) -> list:
    return [line.split("#", 1)[0].strip() for line in body.splitlines()]


class TestStructure:
    def test_call_site_in_main_is_guarded(self):
        calls = [
            code
            for code in _code_lines(_function_body("main"))
            if "report_bmad_absence" in code
        ]
        assert len(calls) == 1, calls
        assert re.search(r"\|\|\s*true\s*$", calls[0]), calls[0]

    def test_it_is_called_nowhere_else(self):
        text = _INSTALL_SH.read_text(encoding="utf-8")
        calls = [c for c in _code_lines(text) if "report_bmad_absence" in c]
        assert len(calls) == 2, calls  # the definition and the one call in main()

    def test_it_emits_only_through_the_guarded_log_helpers(self):
        for code in _code_lines(_function_body("report_bmad_absence")):
            assert not re.match(r"(echo|printf|step)\b", code), code

    def test_it_runs_the_one_detector_and_adds_no_presence_check(self):
        body = "\n".join(_code_lines(_function_body("report_bmad_absence")))
        assert body.count("detect_bmad_module_state") == 1
        assert "/_bmad" not in body
        assert not re.search(r"\b(local|declare)\s+\w+=\$\(", body)

    def test_no_version_shaped_string_in_the_render_path(self):
        assert re.findall(r"\d+\.\d+", _function_body("report_bmad_absence")) == []

    def test_the_detector_and_reporter_are_unchanged(self):
        """Their bodies are pinned by digest: this change may not touch them."""
        import hashlib

        digests = {
            name: hashlib.sha256(_function_body(name).encode("utf-8")).hexdigest()[:16]
            for name in ("detect_bmad_module_state", "report_bmad_module_state")
        }
        assert digests == {
            "detect_bmad_module_state": _DETECTOR_DIGEST,
            "report_bmad_module_state": _REPORTER_DIGEST,
        }


_DETECTOR_DIGEST = "b4b92c8afc9a0bc0"
_REPORTER_DIGEST = "828253313f5b604e"


def _source_with_target(cwd: Path, product: Path, *args: str):
    """Source the no-`main` copy with a project-path argument, then report."""
    quoted = " ".join(f'"{a}"' for a in args)
    bash_cmd = f"""
set -euo pipefail
source "{product}/scripts/install.sh" {quoted}
echo "PROJECT_PATH=$PROJECT_PATH"
report_bmad_module_state "$PROJECT_PATH"
echo "REACHED_END=yes"
"""
    return subprocess.run(
        ["bash", "-c", bash_cmd], capture_output=True, text=True, env=_env(), cwd=cwd
    )


@pytest.fixture
def unsearchable_directory(tmp_path):
    """A directory that cannot be entered.

    FAILS — does not skip — where permissions are not enforced (as root, or on a
    filesystem that ignores mode bits): a skip would be silently green over a
    case that was never exercised.
    """
    target = tmp_path / "sample-unsearchable"
    target.mkdir()
    target.chmod(0o000)
    entered = subprocess.run(["bash", "-c", f'cd "{target}"'], capture_output=True)
    if entered.returncode == 0:
        target.chmod(0o755)
        pytest.fail(
            "cannot construct a directory that refuses entry: this user or "
            f"filesystem does not enforce directory permissions at {target}."
        )
    yield target
    target.chmod(0o755)


class TestProjectPathThatCannotBeEntered:
    def _assert_stopped(self, result, given: str):
        assert result.returncode != 0
        assert given in result.stderr
        assert result.stdout == "", result.stdout
        assert "REACHED_END" not in result.stdout
        assert "BMAD" not in result.stdout + result.stderr
        assert len(result.stderr.strip().splitlines()) == 1, result.stderr

    def test_a_path_that_does_not_exist_stops_the_installer(self, product, tmp_path):
        given = str(tmp_path / "sample-missing")
        self._assert_stopped(_source_with_target(tmp_path, product, given), given)

    def test_a_relative_path_that_does_not_exist_is_named_as_typed(
        self, product, tmp_path
    ):
        result = _source_with_target(tmp_path, product, "sample-typo")
        self._assert_stopped(result, "sample-typo")

    def test_a_regular_file_stops_the_installer(self, product, tmp_path):
        given = tmp_path / "sample-file"
        given.write_text("not a directory\n", encoding="utf-8")
        self._assert_stopped(
            _source_with_target(tmp_path, product, str(given)), str(given)
        )

    def test_a_directory_without_search_permission_stops_the_installer(
        self, product, tmp_path, unsearchable_directory
    ):
        given = str(unsearchable_directory)
        self._assert_stopped(_source_with_target(tmp_path, product, given), given)

    def test_no_argument_still_means_the_current_directory(self, product, tmp_path):
        cwd = _project(tmp_path)
        result = _source_with_target(cwd, product)
        assert result.returncode == 0, result.stderr
        assert f"PROJECT_PATH={cwd}" in result.stdout.splitlines()
        assert "REACHED_END=yes" in result.stdout

    def test_a_relative_path_still_resolves_to_an_absolute_one(self, product, tmp_path):
        target = _project(tmp_path)
        result = _source_with_target(tmp_path, product, target.name)
        assert result.returncode == 0, result.stderr
        assert f"PROJECT_PATH={target}" in result.stdout.splitlines()
        assert "REACHED_END=yes" in result.stdout

    def test_the_stop_applies_with_the_template_check_flag(self, product, tmp_path):
        given = str(tmp_path / "sample-missing")
        result = _source_with_target(tmp_path, product, "--check-templates", given)
        self._assert_stopped(result, given)

    def test_an_empty_target_stops_the_installer(self, product, tmp_path):
        cwd = _project(tmp_path)
        result = _source_with_target(cwd, product, "")
        self._assert_stopped(result, "Cannot enter project path")

    def test_an_empty_target_stops_with_the_template_check_flag(
        self, product, tmp_path
    ):
        cwd = _project(tmp_path)
        result = _source_with_target(cwd, product, "--check-templates", "")
        self._assert_stopped(result, "Cannot enter project path")

"""Every pytest invocation in CI must be behind an executed-test floor.

GR-01 asks for the floor as *shared infrastructure*, not per-suite patches, and
the difference between those two is enforcement. A sweep done once is a
remembered string: the next workflow someone adds is ungated, nothing says so,
and the class quietly reopens -- which is how BUG-536 came to sit beside
BUG-535 undetected.

So the sweep is a mechanism instead. This walks ``.github/workflows/*.yml``,
finds every pytest invocation, and fails when one is not gated. The pattern is
the one already proven by ``tests/test_ci_schema_parity.py``: assert a property
of the workflow files themselves, so drift fails a test rather than shipping.

A job is gated when, for every JUnit report its pytest steps write, some later
step in the same job feeds that report to a floor checker -- either
``tests/ci_executed_floor.py`` directly, or ``tests/datastore_tripwire.py
--check``, which evaluates the same floor via the same shared code.
"""

import re
from pathlib import Path

import pytest
import yaml

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / ".github" / "workflows"

# A pytest invocation in command position: `pytest ...` or `python -m pytest`.
# The negative lookbehind keeps it from matching inside a longer token such as a
# path fragment, and `pip install pytest` lines are dropped separately below.
_PYTEST = re.compile(r"(?<![\w./-])(?:python[\d.]*\s+-m\s+)?pytest(?=\s|$)")

# Producers write a report; consumers read one. `--junit` must not swallow
# `--junitxml`, hence the lookahead on the consumer pattern.
_PRODUCES = re.compile(r"--junit-?xml[= ]\s*([^\s\\]+)")
_CONSUMES = re.compile(r"--junit(?![-\w])[= ]\s*([^\s\\]+)")

_FLOOR_CHECKERS = ("ci_executed_floor.py", "datastore_tripwire.py")


def _workflow_files():
    return sorted(WORKFLOWS_DIR.glob("*.yml")) + sorted(WORKFLOWS_DIR.glob("*.yaml"))


def _run_blocks(workflow_path):
    """Yield (job_name, step_name, run_text) for every step that runs a command."""
    document = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        return
    for job_name, job in (document.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            run = step.get("run")
            if isinstance(run, str):
                yield job_name, step.get("name", "<unnamed step>"), run


def _command_lines(run_text):
    """Drop comment lines so prose mentioning pytest is not read as a command."""
    lines = []
    for line in run_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


def _invokes_pytest(run_text):
    return any(
        _PYTEST.search(line)
        and "pip install" not in line
        and "pip3 install" not in line
        for line in _command_lines(run_text)
    )


def _paths(pattern, run_text):
    return {
        match.group(1).strip("'\"")
        for line in _command_lines(run_text)
        for match in pattern.finditer(line)
    }


def _jobs_running_pytest():
    """Map (workflow, job) -> {"produced": set, "consumed": set, "steps": [...]}."""
    jobs = {}
    for path in _workflow_files():
        for job_name, step_name, run in _run_blocks(path):
            key = (path.name, job_name)
            if _invokes_pytest(run):
                entry = jobs.setdefault(
                    key, {"produced": set(), "consumed": set(), "steps": []}
                )
                entry["steps"].append(step_name)
                entry["produced"] |= _paths(_PRODUCES, run)
            if any(checker in run for checker in _FLOOR_CHECKERS):
                entry = jobs.setdefault(
                    key, {"produced": set(), "consumed": set(), "steps": []}
                )
                entry["consumed"] |= _paths(_CONSUMES, run)
    return jobs


def test_workflows_directory_is_found():
    """A silent zero-workflow sweep would make every test below vacuous."""
    assert WORKFLOWS_DIR.is_dir(), f"no workflows directory at {WORKFLOWS_DIR}"
    assert _workflow_files(), f"no workflow files under {WORKFLOWS_DIR}"


def test_at_least_one_pytest_invocation_is_detected():
    """Guards the detector itself.

    If the regex stops matching -- a syntax change, a refactor -- every
    assertion below passes trivially over an empty set, and the gate reports
    green while checking nothing. That is the failure mode this whole file
    exists to prevent, so it is asserted here too.
    """
    assert _jobs_running_pytest(), (
        "no pytest invocations found in any workflow. Either CI stopped running "
        "tests, or the detector in this file no longer matches how they are "
        "invoked -- in which case this gate is passing vacuously."
    )


@pytest.mark.parametrize(
    "workflow,job",
    sorted(_jobs_running_pytest()),
    ids=lambda value: str(value).replace(".yml", ""),
)
def test_every_pytest_job_writes_a_junit_report(workflow, job):
    entry = _jobs_running_pytest()[(workflow, job)]
    if not entry["steps"]:
        pytest.skip("this job checks a floor but does not run pytest itself")
    assert entry["produced"], (
        f"{workflow} job {job!r} runs pytest (steps: {entry['steps']}) but no "
        "step emits a JUnit report. Add --junitxml=<file> so the number of "
        "tests that actually ran can be checked. GR-01: a green is a claim "
        "about what RAN."
    )


@pytest.mark.parametrize(
    "workflow,job",
    sorted(_jobs_running_pytest()),
    ids=lambda value: str(value).replace(".yml", ""),
)
def test_every_junit_report_is_gated_by_the_floor(workflow, job):
    entry = _jobs_running_pytest()[(workflow, job)]
    if not entry["steps"]:
        pytest.skip("this job checks a floor but does not run pytest itself")
    ungated = entry["produced"] - entry["consumed"]
    assert not ungated, (
        f"{workflow} job {job!r} writes JUnit report(s) {sorted(ungated)} that "
        "no step checks. Add a step running "
        "`python3 tests/ci_executed_floor.py --junit <file> --min-executed <N>`. "
        "An unchecked report is not a floor -- the job still passes when the "
        "suite executes nothing (BUG-536)."
    )

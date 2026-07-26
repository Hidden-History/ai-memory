"""CI pytest marker-expression override gate -- TD-898 / PLAN-038 Sec2 P2.

pytest's `-m` is single-valued: a workflow step's own `-m EXPR` REPLACES
pyproject.toml's `addopts = "... -m 'not regression'"`, it does not AND with
it. Any CI `pytest` invocation that supplies its own `-m` therefore silently
drops the `not regression` exclusion unless its own expression also names
it -- re-enabling tests marked `regression` ("Regression tests requiring
live Langfuse + Qdrant") in CI (TD-898). The defective command originated in
Parzival's own auto-memory, was copied into CI, and was then adopted
verbatim by a best-practice document -- this gate exists so the fix is a
mechanism, not a remembered string.

GLOBS `.github/workflows/*.yml` (never enumerates filenames) so a new
workflow file is checked automatically.

Matcher scope, stated explicitly (an unstated matcher's completeness claim
is unsupportable even when the answer happens to be right):
  - Recognizes a shell command that starts with the literal token `pytest`,
    after joining backslash-continued lines into one logical line. This
    structurally excludes `python -m pip`, `python -m build`, and
    `install -m 0755` -- none of them start with `pytest`.
  - Does NOT recognize the `python -m pytest ...` module-invocation form.
    No such invocation exists in this repo today; if one is added, this
    gate will silently miss it.
  - Only inspects YAML-mapping `run:` step values (both block-scalar and
    plain-string forms). It does not follow `uses:`-based composite
    actions or reusable workflow calls.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO / ".github" / "workflows"

# Deliberate live-regression runners: their bare `-m regression` (no "not")
# intentionally NARROWS the run to *only* the regression suite -- that is
# each job's entire purpose (gated behind live Langfuse/Qdrant secrets), not
# an accidental override of the baseline `not regression` exclusion. Keyed
# on (workflow filename, exact marker expression) so it stays narrow: a new,
# different `-m` on either file is not covered and must fail the gate.
DELIBERATE_REGRESSION_RUNNERS = {
    ("regression-tests.yml", "regression"),
    ("regression-nightly.yml", "regression"),
}

# A `pytest` command word: start of a logical line, or after a shell
# separator (`;`, `&&`, `||`, `|`).
_PYTEST_INVOCATION_RE = re.compile(
    r"(?:^|[;&|]\s*)pytest\s+(?P<args>[^\n;&|]*)",
    re.MULTILINE,
)

# A `-m` flag (not part of a longer `--...` token) and its quoted-or-bare
# marker expression.
_MARKER_FLAG_RE = re.compile(r"(?<!\S)-m\s+(?:'([^']*)'|\"([^\"]*)\"|(\S+))")


def _join_line_continuations(run_text: str) -> str:
    """Collapse shell `\\\n` continuations into spaces so a multi-line
    pytest invocation reads as one logical line for the regexes above."""
    return re.sub(r"\\\s*\n\s*", " ", run_text)


def _iter_run_blocks(yaml_path: Path):
    """Yield every `run:` shell string from a workflow file's jobs/steps."""
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    jobs = (data or {}).get("jobs") or {}
    for job in jobs.values():
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            run = step.get("run")
            if isinstance(run, str):
                yield run


def find_pytest_invocations(yaml_path: Path) -> list[tuple[str, str | None]]:
    """Return (invocation_text, marker_expr_or_None) for every `pytest ...`
    command in the file's `run:` blocks. `marker_expr` is None when no `-m`
    flag is present (a safe invocation -- it inherits addopts)."""
    results = []
    for run_text in _iter_run_blocks(yaml_path):
        joined = _join_line_continuations(run_text)
        for match in _PYTEST_INVOCATION_RE.finditer(joined):
            args = match.group("args")
            marker_match = _MARKER_FLAG_RE.search(args)
            marker = None
            if marker_match:
                marker = next(g for g in marker_match.groups() if g is not None)
            results.append((match.group(0).strip(), marker))
    return results


def check_marker_expression(yaml_path: Path) -> list[str]:
    """Return violation messages for every unsafe `-m` override in one file."""
    violations = []
    for invocation, marker in find_pytest_invocations(yaml_path):
        if marker is None:
            continue  # no -m -> inherits addopts' "not regression" -> safe
        if "not regression" in marker:
            continue  # preserves the baseline exclusion -> safe
        if (yaml_path.name, marker) in DELIBERATE_REGRESSION_RUNNERS:
            continue  # narrow, commented allowlist above -> safe
        violations.append(
            f'{yaml_path.name}: `{invocation}` -- `-m "{marker}"` REPLACES '
            "addopts' `-m 'not regression'` instead of ANDing with it "
            "(TD-898), re-enabling the live-Langfuse+Qdrant regression "
            "tests. Add `not regression` to the expression, or add "
            "(filename, expression) to DELIBERATE_REGRESSION_RUNNERS with a "
            "stated reason if this is intentionally a live-regression "
            "runner."
        )
    return violations


def test_no_marker_override_across_workflows():
    """Every `pytest -m ...` invocation in .github/workflows/*.yml must
    preserve `not regression`, or be a narrowly allowlisted deliberate
    regression runner. Globs the directory so a new workflow file is
    checked automatically -- PLAN-038 Sec2 P2."""
    all_violations = []
    for yaml_path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        all_violations.extend(check_marker_expression(yaml_path))
    assert all_violations == [], "\n".join(all_violations)


def test_deliberate_runners_still_present():
    """Guard the allowlist itself: if a listed regression runner is
    renamed or its expression changes, the allowlist entry goes stale
    silently unless something asserts it is still backed by a real
    invocation."""
    for filename, expr in sorted(DELIBERATE_REGRESSION_RUNNERS):
        path = WORKFLOWS_DIR / filename
        assert path.exists(), f"allowlisted workflow {filename} no longer exists"
        markers = [m for _, m in find_pytest_invocations(path)]
        assert expr in markers, (
            f"{filename} no longer contains a pytest invocation with "
            f"`-m {expr!r}` -- update or remove the DELIBERATE_REGRESSION_RUNNERS entry"
        )


def test_no_marker_flag_is_safe(tmp_path):
    workflow = tmp_path / "clean.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        "      - run: |\n"
        "          pytest tests/ -v --tb=short\n"
    )
    assert check_marker_expression(workflow) == []


def test_bare_not_quarantine_is_flagged(tmp_path):
    """Reproduces the exact TD-898 defect on a synthetic file."""
    workflow = tmp_path / "bad.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        "      - run: |\n"
        "          pytest tests/ -v --tb=short \\\n"
        '            -m "not quarantine" \\\n'
        "            -p no:randomly\n"
    )
    violations = check_marker_expression(workflow)
    assert len(violations) == 1
    assert "not quarantine" in violations[0]


def test_not_regression_and_x_is_safe(tmp_path):
    workflow = tmp_path / "fixed.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        '      - run: pytest tests/ -m "not regression and not quarantine"\n'
    )
    assert check_marker_expression(workflow) == []


def test_unregistered_bare_regression_is_flagged(tmp_path):
    """A file NOT in DELIBERATE_REGRESSION_RUNNERS using bare `-m regression`
    must still fail -- the allowlist is keyed on filename, not the marker
    expression alone."""
    workflow = tmp_path / "not-allowlisted.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        "      - run: pytest tests/test_regression.py -m regression\n"
    )
    violations = check_marker_expression(workflow)
    assert len(violations) == 1


def test_python_module_invocations_are_not_pytest_commands(tmp_path):
    """`python -m pip`, `python -m build`, and `install -m 0755` are not
    pytest marker expressions and must not trip the gate."""
    workflow = tmp_path / "installs.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        "      - run: |\n"
        "          python -m pip install --upgrade pip\n"
        "          python -m build\n"
        "          install -m 0755 script.sh /usr/local/bin/script.sh\n"
    )
    assert check_marker_expression(workflow) == []


def test_line_continuation_invocation_is_detected(tmp_path):
    """Confirms the matcher handles the real shape of the defect: `-m` on
    its own continuation line, separate from the `pytest` token's line."""
    workflow = tmp_path / "continued.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        "      - run: |\n"
        "          pytest tests/integration -v --tb=short \\\n"
        "            --run-integration \\\n"
        '            -m "not requires_embedding"\n'
    )
    violations = check_marker_expression(workflow)
    assert len(violations) == 1
    assert "not requires_embedding" in violations[0]

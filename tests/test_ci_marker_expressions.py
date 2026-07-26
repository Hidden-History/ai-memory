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

GLOBS `.github/workflows/*.yml` and `*.yaml` (never enumerates filenames) so
a new workflow file is checked automatically regardless of which extension
it uses.

Matcher scope, stated explicitly (an unstated matcher's completeness claim
is unsupportable even when the answer happens to be right):
  - Recognizes all three forms the repo already treats as equivalent
    pytest invocations (`tests/test_error_context_retrieval.py`'s
    BUILD_TEST_PATTERNS["pytest"]): bare `pytest ...`, `python -m
    pytest ...`, and `python3 -m pytest ...` -- after joining
    backslash-continued lines into one logical line. This structurally
    excludes `python -m pip`, `python -m build`, and `install -m 0755`:
    none of them have the literal token `pytest` immediately after an
    optional `python[3] -m `.
  - Does NOT recognize a pytest invocation reached through a shell
    variable, alias, or wrapper script (e.g. `$PYTEST_BIN tests/`, or a
    Makefile target that itself calls pytest) -- no regex over the
    workflow YAML can see through that indirection. No such indirection
    exists in this repo's workflows today.
  - Does NOT recognize a path-prefixed pytest binary (e.g.
    `./venv/bin/pytest tests/ -m "not quarantine"` or `/usr/bin/pytest
    ...`) -- the lookbehind that keeps the matcher from firing inside a
    larger word also excludes a preceding `/` or `.`. This is a literal
    pytest invocation, not indirection, and is a more plausible future
    form than an alias. No such invocation exists in this repo's
    workflows today.
  - DELIBERATELY over-matches inside shell comments and quoted prose
    (e.g. a commented-out `# pytest tests/ -m "not quarantine"`, or
    `echo "we run pytest tests/ -m foo"`) -- the matcher has no notion of
    shell comment or quoting context. This is a deliberate fail-loud
    bias, not an oversight: a false positive here fails CI loudly and
    gets fixed; a false negative would silently run the live-service
    tests in CI, which is the TD-898 harm this gate exists to prevent.
    Narrowing the anchor to eliminate the over-match would reopen that
    false-negative risk, so it is intentionally left as-is. No such
    comment or prose exists in this repo's workflows today.
  - Inspects YAML-mapping `run:` step values (both block-scalar and
    plain-string forms), AND `env: PYTEST_ADDOPTS` at workflow-, job-,
    and step-scope -- a `pytest` invocation with no `-m` of its own is
    still overridden if `PYTEST_ADDOPTS` carries one, and that override
    is invisible to anything that only reads `run:` text. Each scope's
    `PYTEST_ADDOPTS` is checked independently; GitHub Actions' own
    env-scope precedence (step overrides job overrides workflow) is not
    modelled, so a shadowed, ineffective `PYTEST_ADDOPTS` at a broader
    scope can still be reported alongside the one that actually wins --
    over-reporting, never under-reporting, which matches this gate's
    fail-loud bias. It does not follow `uses:`-based composite actions
    or reusable workflow calls.
  - Also recognizes `PYTEST_ADDOPTS` set directly in shell text within a
    `run:` block -- as an inline prefix on the pytest command itself
    (`PYTEST_ADDOPTS='-m "..."' pytest ...`), an `export PYTEST_ADDOPTS=...`
    statement earlier in the same block, or a `>> "$GITHUB_ENV"` write for
    a later step -- none of which appear as a YAML `env:` mapping and so
    would otherwise be invisible to the scope above.
  - Recognizes `-m` in every form pytest's own argument parser resolves
    to the `markexpr` value (verified against the installed pytest via
    `_pytest.config.get_config()._parser.parse_known_and_unknown_args`):
    space-separated (`-m "expr"`), attached-quoted (`-m"expr"`),
    `=`-separated (`-m="expr"`), and bare-attached (`-mexpr`). It does
    NOT recognize `-m` bundled into a combined short-option cluster where
    `-m` is not the cluster's own leading dash (e.g. `-vm "expr"`) --
    pytest's argparse does resolve this at runtime, but matching it
    without a full short-option grammar risks misreading unrelated
    dash-prefixed tokens. No such combined-flag invocation exists in this
    repo's workflows today.
  - The bare-attached form (`-mexpr`, no space/`=`) is only recognized up
    to the first whitespace character: `-mnot quarantine` captures just
    `not` as the expression, not `not quarantine`, because nothing marks
    where a space-free attached expression ends. The truncated `not` fails
    to parse on its own, so this is over-reported as unsafe (fail-loud),
    never silently accepted -- but it means this form is NOT recognized
    unqualified for any expression containing a space, contrary to what a
    bare reading of the line above might suggest.
  - A `${{ ... }}` GitHub Actions expression inside an `-m` value (e.g. a
    marker driven by a workflow input or matrix variable) is not resolved
    -- the literal `${{ ... }}` text is handed to pytest's expression
    compiler, which rejects the `$`/`{` characters with a `SyntaxError`,
    correctly landing on the unsafe verdict via the same path as any other
    unparseable expression. No such indirection exists in this repo's
    workflows today.
  - When more than one `-m` flag appears on the same invocation (or the
    same `PYTEST_ADDOPTS` value), the LAST one is evaluated -- pytest's
    `-m` is a store action, so a repeated flag has its earlier
    occurrences silently discarded at runtime; reading the first would
    report an override that was never actually in effect.
  - Safety is decided by compiling the expression with pytest's own
    keyword-expression evaluator (`_pytest.mark.expression.Expression`,
    a private API) and checking, for every combination of the other
    identifiers the expression names, whether it can evaluate true while
    `regression` is true. This is an existential check, not a substring
    test: `"not regression" in expr` reads `not regression_slow` (a
    distinct identifier) as containing the exclusion it does not have,
    and reads `not regression or slow` as safe when it in fact selects a
    regression-marked test that is also marked `slow`. An expression
    pytest itself cannot parse, or one whose parse tree is too deep for
    Python's recursion limit (`RecursionError`), is treated as unsafe
    (fails loud) rather than skipped. Verified against the pytest version
    installed at authoring time, within this repo's pinned range
    (`pyproject.toml` `pytest>=9.0.3,<10.0.0`); an upstream change to this
    private API inside that range would surface as an import or evaluation
    error in this file, not a silent gap.
  - An EMPTY `markexpr` (`-m ""`) is treated as unsafe, not safe: pytest's
    own `deselect_by_mark` does `if not matchexpr: return`, so an empty `-m`
    performs NO deselection at all and the entire suite -- including every
    `regression`-marked test -- runs. This is a fail-open, not a false
    negative on one expression, and is distinct from a whitespace-only
    `markexpr` (`-m " "`), which IS truthy to that same check and compiles
    to a constant-false expression that correctly deselects everything
    (genuinely safe, if a strange thing to write).
  - The existential check enumerates every combination of the OTHER
    identifiers an expression names, which is O(2^N). An expression naming
    more than 15 other identifiers is treated as unsafe (fail-loud) rather
    than enumerated, to bound this cost -- measured at ~0.2s per expression
    at the cap and ~9s at 20 identifiers, growing exponentially from there.
    No marker expression in this repo's workflows today names more than 2
    other identifiers.
  - A keyword-argument matcher (e.g. `-m "regression and device(serial=
    '1')"`, valid under pytest's `ident kwargs?` `-m` grammar since pytest
    8.4) does not raise: the identifier-truthiness callback accepts and
    discards any kwargs pytest's evaluator passes it, rather than only a
    bare mark name.
"""

from __future__ import annotations

import itertools
import re
from pathlib import Path

import yaml
from _pytest.mark.expression import Expression

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

# A pytest invocation in any of the three forms the repo already treats as
# equivalent (tests/test_error_context_retrieval.py BUILD_TEST_PATTERNS):
# bare `pytest`, `python -m pytest`, `python3 -m pytest`. The lookbehind
# requires a non-identifier boundary before the match (start of string,
# whitespace, quote, or shell separator) so it doesn't fire inside a larger
# word, while still matching regardless of what precedes it on the line
# (e.g. embedded after `unshare -rn ... _ python -m pytest ...`).
_PYTEST_INVOCATION_RE = re.compile(
    r"(?<![\w./-])(?:python3?\s+-m\s+)?pytest\s+(?P<args>[^\n;&|]*)",
    re.MULTILINE,
)

# A `-m` flag (not part of a longer `--...` token) and its marker
# expression, in every form pytest's own argparse resolves to `markexpr`:
# space-separated, attached-quoted, `=`-separated, or bare-attached.
_MARKER_FLAG_RE = re.compile(r"(?<!\S)-m[\s=]*(?:'([^']*)'|\"([^\"]*)\"|(\S+))")

# Identifiers named in a marker expression, for the existential safety
# check below. Boolean keywords are not mark names.
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_EXPRESSION_KEYWORDS = {"and", "or", "not", "True", "False"}

# `PYTEST_ADDOPTS=<rest-of-line>` set directly in shell text within a `run:`
# block -- as an inline prefix on the pytest command itself, an `export`
# statement earlier in the same block, or a `>> "$GITHUB_ENV"` write for a
# later step -- none of which appear as a YAML `env:` mapping, so none of
# them are visible to anything that only reads `env:`. The lookbehind keeps
# this from firing on a longer variable name ending in `_PYTEST_ADDOPTS`.
_SHELL_ADDOPTS_RE = re.compile(r"(?<![A-Za-z0-9_])PYTEST_ADDOPTS=(?P<rest>[^\n]*)")


def _join_line_continuations(run_text: str) -> str:
    """Collapse shell `\\\n` continuations into spaces so a multi-line
    pytest invocation reads as one logical line for the regexes above."""
    return re.sub(r"\\\s*\n\s*", " ", run_text)


def _last_marker_flag(text: str) -> str | None:
    """Return the marker expression from the LAST `-m` flag in `text`, or
    None if absent. pytest's `-m` is a store action: a repeated flag has
    only its last occurrence take effect at runtime."""
    marker = None
    for match in _MARKER_FLAG_RE.finditer(text):
        marker = next(g for g in match.groups() if g is not None)
    return marker


_MAX_MARKER_IDENTIFIERS = 15  # itertools.product below is O(2^N); no marker
# expression in this repo's workflows today names more than 2 other
# identifiers. Measured worst case at N=15 is ~0.2s per expression; N=20
# reaches ~9s, and the growth is exponential from there -- an expression
# over this cap is treated as unsafe (fail-loud) rather than enumerated.


def _selects_regression(marker: str) -> bool:
    """True if `marker` could select a test carrying the `regression` mark,
    for ANY combination of the other identifiers it names. Existential
    over pytest's own keyword-expression evaluator, not a substring test.
    An empty `markexpr` is treated as unsafe: pytest's own `deselect_by_mark`
    does `if not matchexpr: return`, so `-m ""` performs NO deselection and
    the entire suite (including `regression`-marked tests) runs -- unlike a
    whitespace-only expression, which IS truthy to that check and compiles
    to a constant-false expression that correctly deselects everything. A
    syntactically invalid or too-deeply-nested expression is treated as
    unsafe, as is one naming more than `_MAX_MARKER_IDENTIFIERS` other
    identifiers (see cap rationale above)."""
    if not marker:
        return True
    try:
        compiled = Expression.compile(marker)
    except (SyntaxError, RecursionError):
        return True
    identifiers = set(_IDENTIFIER_RE.findall(marker)) - _EXPRESSION_KEYWORDS
    other_identifiers = sorted(identifiers - {"regression"})
    if len(other_identifiers) > _MAX_MARKER_IDENTIFIERS:
        return True
    for combo in itertools.product((False, True), repeat=len(other_identifiers)):
        truthy = dict(zip(other_identifiers, combo, strict=True))
        truthy["regression"] = True
        if compiled.evaluate(
            lambda name, truthy=truthy, **kwargs: truthy.get(name, False)
        ):
            return True
    return False


def _iter_workflow_paths():
    """Yield every workflow file, `.yml` and `.yaml` alike -- GitHub
    honours both extensions, so a matcher that only globs one silently
    stops checking a workflow authored with the other."""
    yield from sorted(
        itertools.chain(WORKFLOWS_DIR.glob("*.yml"), WORKFLOWS_DIR.glob("*.yaml"))
    )


def _iter_run_blocks(yaml_path: Path):
    """Yield every `run:` shell string from a workflow file's jobs/steps."""
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    jobs = (data or {}).get("jobs") or {}
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            run = step.get("run")
            if isinstance(run, str):
                yield run


def _iter_env_blocks(yaml_path: Path):
    """Yield every `env:` mapping at workflow-, job-, and step-scope."""
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    top_env = data.get("env")
    if isinstance(top_env, dict):
        yield top_env
    jobs = data.get("jobs") or {}
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        job_env = job.get("env")
        if isinstance(job_env, dict):
            yield job_env
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            step_env = step.get("env")
            if isinstance(step_env, dict):
                yield step_env


def find_pytest_invocations(yaml_path: Path) -> list[tuple[str, str | None]]:
    """Return (invocation_text, marker_expr_or_None) for every `pytest ...`
    command in the file's `run:` blocks. `marker_expr` is None when no `-m`
    flag is present (a safe invocation -- it inherits addopts)."""
    results = []
    for run_text in _iter_run_blocks(yaml_path):
        joined = _join_line_continuations(run_text)
        for match in _PYTEST_INVOCATION_RE.finditer(joined):
            args = match.group("args")
            marker = _last_marker_flag(args)
            results.append((match.group(0).strip(), marker))
    return results


def _shell_set_addopts(run_text: str) -> list[str]:
    """Return every `PYTEST_ADDOPTS` value set directly in shell text within
    a `run:` block -- an inline prefix on the pytest command itself, an
    `export PYTEST_ADDOPTS=...` statement earlier in the block, or a
    `>> "$GITHUB_ENV"` write for a later step. A leading quote character is
    stripped so the value reads the same as an unwrapped YAML `env:` value;
    a trailing shell artefact (closing quote, `>> "$GITHUB_ENV"`, a
    following ` pytest ...`) is left in place but does not affect
    `_last_marker_flag`, which only looks for its own `-m` pattern."""
    values = []
    for match in _SHELL_ADDOPTS_RE.finditer(run_text):
        rest = match.group("rest")
        if rest[:1] in ("'", '"'):
            rest = rest[1:]
        values.append(rest)
    return values


def find_pytest_addopts_markers(yaml_path: Path) -> list[tuple[str, str | None]]:
    """Return (addopts_text, marker_expr_or_None) for every `PYTEST_ADDOPTS`
    value found at workflow-, job-, or step-scope -- via a YAML `env:`
    mapping, or set directly in shell text within a `run:` block (inline
    prefix, `export`, or a `>> "$GITHUB_ENV"` write)."""
    results = []
    for env in _iter_env_blocks(yaml_path):
        value = env.get("PYTEST_ADDOPTS")
        if not isinstance(value, str):
            continue
        results.append((value, _last_marker_flag(value)))
    for run_text in _iter_run_blocks(yaml_path):
        joined = _join_line_continuations(run_text)
        for value in _shell_set_addopts(joined):
            results.append((value, _last_marker_flag(value)))
    return results


def check_marker_expression(yaml_path: Path) -> list[str]:
    """Return violation messages for every unsafe `-m` override in one file,
    whether supplied on the `pytest` command line or via `PYTEST_ADDOPTS`."""
    violations = []

    def _record(invocation: str, marker: str | None) -> None:
        if marker is None:
            return  # no -m -> inherits addopts' "not regression" -> safe
        if not _selects_regression(marker):
            return  # cannot select a regression-marked test -> safe
        if (yaml_path.name, marker) in DELIBERATE_REGRESSION_RUNNERS:
            return  # narrow, commented allowlist above -> safe
        violations.append(
            f'{yaml_path.name}: `{invocation}` -- `-m "{marker}"` REPLACES '
            "addopts' `-m 'not regression'` instead of ANDing with it "
            "(TD-898), re-enabling the live-Langfuse+Qdrant regression "
            "tests. Add `not regression` to the expression, or add "
            "(filename, expression) to DELIBERATE_REGRESSION_RUNNERS with a "
            "stated reason if this is intentionally a live-regression "
            "runner."
        )

    for invocation, marker in find_pytest_invocations(yaml_path):
        _record(invocation, marker)
    for addopts_text, marker in find_pytest_addopts_markers(yaml_path):
        _record(f"env PYTEST_ADDOPTS: {addopts_text!r}", marker)
    return violations


def test_no_marker_override_across_workflows():
    """Every `pytest -m ...` invocation (command-line or `PYTEST_ADDOPTS`)
    in .github/workflows/*.yml or *.yaml must preserve `not regression`, or
    be a narrowly allowlisted deliberate regression runner. Globs the
    directory so a new workflow file is checked automatically -- PLAN-038
    Sec2 P2."""
    all_violations = []
    for yaml_path in _iter_workflow_paths():
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


def test_python_dash_m_pytest_form_is_detected(tmp_path):
    """`python -m pytest ...` and `python3 -m pytest ...` must be
    recognized as pytest invocations (matches
    tests/test_error_context_retrieval.py's BUILD_TEST_PATTERNS["pytest"]
    definition), not just the bare `pytest ...` form."""
    workflow = tmp_path / "module_form.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        '      - run: python -m pytest tests/ -m "not quarantine"\n'
        '      - run: python3 -m pytest tests/ -m "not quarantine"\n'
    )
    violations = check_marker_expression(workflow)
    assert len(violations) == 2


def test_python_dash_m_pytest_embedded_after_wrapper_is_detected(tmp_path):
    """Reproduces the exact shape used by this project's own safety
    instruction for running gate tests in a network-isolated namespace:
    `unshare -rn sh -c '...' _ python -m pytest ... -m "not quarantine"`.
    The pytest invocation is not at the start of the line or after a
    shell separator here -- it follows a bare positional argument -- so
    the matcher must not require either of those anchors."""
    workflow = tmp_path / "wrapped.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        "      - run: |\n"
        "          unshare -rn sh -c 'ip link set lo up && exec \"$@\"' _ \\\n"
        '            python -m pytest tests/ -m "not quarantine"\n'
    )
    violations = check_marker_expression(workflow)
    assert len(violations) == 1
    assert "not quarantine" in violations[0]


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


def test_yaml_extension_workflow_is_checked(tmp_path, monkeypatch):
    """G1: a workflow authored as `*.yaml` (GitHub honours both `.yml` and
    `.yaml`) must be discovered by the same glob that checks `*.yml`."""
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yaml").write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        '      - run: pytest tests/ -m "not quarantine"\n'
    )
    monkeypatch.setattr("tests.test_ci_marker_expressions.WORKFLOWS_DIR", workflows_dir)
    all_violations = []
    for yaml_path in _iter_workflow_paths():
        all_violations.extend(check_marker_expression(yaml_path))
    assert len(all_violations) == 1
    assert "not quarantine" in all_violations[0]


def test_attached_and_equals_marker_flags_are_detected(tmp_path):
    """G2: `-m"expr"` (attached, no space) and `-m="expr"` (`=`-separated)
    both resolve to the same `markexpr` as `-m "expr"` in pytest's own
    argparse -- the matcher must recognize both, not just the
    space-separated form."""
    workflow = tmp_path / "attached.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        '      - run: pytest tests/ -m"not quarantine"\n'
        '      - run: pytest tests/ -m="not quarantine"\n'
    )
    violations = check_marker_expression(workflow)
    assert len(violations) == 2


def test_substring_collision_regression_slow_is_flagged(tmp_path):
    """G3: `not regression_slow` is a DIFFERENT identifier from
    `regression` and excludes nothing named `regression` -- the raw
    substring test `"not regression" in expr` was fooled by this because
    "not regression" is a text prefix of "not regression_slow"."""
    workflow = tmp_path / "collision.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        '      - run: pytest tests/ -m "not regression_slow and not quarantine"\n'
    )
    violations = check_marker_expression(workflow)
    assert len(violations) == 1
    assert "regression_slow" in violations[0]


def test_conditionally_unsafe_or_expression_is_flagged(tmp_path):
    """G3: `not regression or slow` excludes `regression` only when the
    test is NOT also marked `slow` -- a regression test that is also
    marked `slow` is still selected. A substring test reads this as safe
    (it contains "not regression"); the existential evaluator must not."""
    workflow = tmp_path / "or_expr.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        '      - run: pytest tests/ -m "not regression or slow"\n'
    )
    violations = check_marker_expression(workflow)
    assert len(violations) == 1
    assert "not regression or slow" in violations[0]


def test_double_negative_regression_only_is_flagged(tmp_path):
    """G3: `not (not regression)` selects ONLY regression-marked tests --
    the substring test never sees "not regression" as a standalone
    exclusion here (it is wrapped in an outer negation) and would have
    reported this as safe by accident (no "-m" text match at all applies
    here since the substring IS present, but the semantics are inverted)."""
    workflow = tmp_path / "double_negative.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        '      - run: pytest tests/ -m "not (not regression)"\n'
    )
    violations = check_marker_expression(workflow)
    assert len(violations) == 1


def test_last_of_repeated_marker_flag_is_evaluated(tmp_path):
    """G4: pytest's `-m` is a store action -- when repeated, only the LAST
    occurrence is in effect at runtime. `-m "not regression" -m "not
    quarantine"` actually runs with `not quarantine`, dropping the
    regression exclusion, even though the first (unused) `-m` looks safe."""
    workflow = tmp_path / "repeated.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        '      - run: pytest tests/ -m "not regression" -m "not quarantine"\n'
    )
    violations = check_marker_expression(workflow)
    assert len(violations) == 1
    assert "not quarantine" in violations[0]


def test_pytest_addopts_env_override_is_flagged(tmp_path):
    """G5: `PYTEST_ADDOPTS` overrides `addopts` the same way a `-m` on the
    command line does. A `run:` step with no `-m` at all is still unsafe
    if its step's `env: PYTEST_ADDOPTS` carries one -- invisible to
    anything that only inspects `run:` text."""
    workflow = tmp_path / "addopts.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        "      - run: pytest tests/ -v\n"
        "        env:\n"
        "          PYTEST_ADDOPTS: '-m \"not quarantine\"'\n"
    )
    violations = check_marker_expression(workflow)
    assert len(violations) == 1
    assert "PYTEST_ADDOPTS" in violations[0]


def test_pytest_addopts_env_at_job_and_workflow_scope_is_flagged(tmp_path):
    """G5: `PYTEST_ADDOPTS` set at job- or workflow-scope applies to every
    step's pytest invocation in that scope, not just a step carrying its
    own `env:` block."""
    workflow = tmp_path / "addopts_scopes.yml"
    workflow.write_text(
        "env:\n"
        "  PYTEST_ADDOPTS: '-m \"not quarantine\"'\n"
        "jobs:\n"
        "  unit:\n"
        "    env:\n"
        "      PYTEST_ADDOPTS: '-m \"not requires_embedding\"'\n"
        "    steps:\n"
        "      - run: pytest tests/ -v\n"
    )
    violations = check_marker_expression(workflow)
    assert len(violations) == 2


def test_pytest_addopts_env_safe_value_does_not_flag(tmp_path):
    workflow = tmp_path / "addopts_safe.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        "      - run: pytest tests/ -v\n"
        "        env:\n"
        "          PYTEST_ADDOPTS: '-m \"not regression and not quarantine\"'\n"
    )
    assert check_marker_expression(workflow) == []


def test_empty_marker_expression_is_unsafe(tmp_path):
    """F1 (CRITICAL): pytest's own `deselect_by_mark` does `if not matchexpr:
    return` -- an empty `-m ""` performs NO deselection at all, so the ENTIRE
    suite (including `regression`-marked tests) runs. `Expression.compile("")`
    is structurally constant-false, which would score every enumerated
    combination as safe if the existential check ran at all -- this is a
    fail-open, not merely a false-negative on one expression."""
    workflow = tmp_path / "empty_marker.yml"
    workflow.write_text(
        "jobs:\n" "  unit:\n" "    steps:\n" '      - run: pytest tests/ -m ""\n'
    )
    violations = check_marker_expression(workflow)
    assert len(violations) == 1


def test_whitespace_only_marker_expression_is_safe(tmp_path):
    """F1: `-m " "` is a non-empty string, so it IS truthy to pytest's `if
    not matchexpr: return` check -- pytest proceeds to compile and evaluate
    it, and a whitespace-only expression is constant-false, so it correctly
    deselects every test (including any `regression`-marked ones). This is
    the case that must NOT be conflated with the empty-string fail-open
    above: the two look similar as text but behave oppositely at runtime."""
    workflow = tmp_path / "whitespace_marker.yml"
    workflow.write_text(
        "jobs:\n" "  unit:\n" "    steps:\n" '      - run: pytest tests/ -m " "\n'
    )
    assert check_marker_expression(workflow) == []


def test_marker_expression_identifier_count_is_capped(tmp_path):
    """F2: `itertools.product` over the other identifiers an expression
    names is O(2^N). An expression naming more identifiers than the cap
    must be treated as UNSAFE (fail-loud) rather than enumerated -- silently
    skipping it would reopen a false-negative, and enumerating it risks the
    CI job's own timeout. The identifiers are AND-ed together (not OR-ed) so
    only the single all-True combination -- the LAST one `itertools.product`
    would enumerate -- satisfies the expression; an implementation that
    enumerates instead of capping cannot short-circuit early on this shape,
    so the wall-clock assertion below actually exercises the cap rather than
    an incidental early exit."""
    many_ids = " and ".join(f"id{i}" for i in range(18))
    expr = f"regression and {many_ids}"
    workflow = tmp_path / "too_many_identifiers.yml"
    workflow.write_text(
        "jobs:\n" "  unit:\n" "    steps:\n" f'      - run: pytest tests/ -m "{expr}"\n'
    )
    import time

    start = time.time()
    violations = check_marker_expression(workflow)
    elapsed = time.time() - start
    assert len(violations) == 1
    assert elapsed < 2.0, f"identifier cap did not bound enumeration cost ({elapsed}s)"


def test_shell_inline_pytest_addopts_prefix_is_flagged(tmp_path):
    """F3: `PYTEST_ADDOPTS='...' pytest ...` sets the override as a shell
    variable prefix on the same command -- the `-m` inside it sits in `run:`
    text the gate already reads, just outside the invocation regex's `args`
    span (it precedes the `pytest` token rather than following it)."""
    workflow = tmp_path / "inline_addopts.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        "      - run: PYTEST_ADDOPTS='-m \"not quarantine\"' pytest tests/\n"
    )
    violations = check_marker_expression(workflow)
    assert len(violations) == 1
    assert "not quarantine" in violations[0]


def test_shell_export_pytest_addopts_is_flagged(tmp_path):
    """F3: `export PYTEST_ADDOPTS=...` on its own line, followed by a bare
    `pytest` invocation later in the same `run:` block, is the canonical
    shell idiom for setting env ahead of a command -- and is invisible to
    a matcher that only reads YAML `env:` mappings."""
    workflow = tmp_path / "export_addopts.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        "      - run: |\n"
        "          export PYTEST_ADDOPTS='-m \"not quarantine\"'\n"
        "          pytest tests/\n"
    )
    violations = check_marker_expression(workflow)
    assert len(violations) == 1
    assert "not quarantine" in violations[0]


def test_github_env_pytest_addopts_is_flagged(tmp_path):
    """F3: writing `PYTEST_ADDOPTS=...` to `$GITHUB_ENV` in one step makes it
    part of every later step's environment in the same job -- the canonical
    GitHub Actions idiom for cross-step env, and invisible to anything that
    only reads YAML `env:` mappings since it never appears as one."""
    workflow = tmp_path / "github_env_addopts.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        '      - run: echo \'PYTEST_ADDOPTS=-m "not quarantine"\' >> "$GITHUB_ENV"\n'
        "      - run: pytest tests/\n"
    )
    violations = check_marker_expression(workflow)
    assert len(violations) == 1
    assert "not quarantine" in violations[0]


def test_kwargs_matcher_expression_does_not_crash(tmp_path):
    """F4: pytest >=8.4's `-m` grammar allows `ident kwargs?` (e.g. keyword
    matchers). The existential check's identifier-truthiness lambda must
    accept and ignore kwargs rather than raising `TypeError` -- a crash here
    is not a safety hole, but it is undocumented and contradicts the
    docstring's claim that only unparseable expressions get special
    handling."""
    workflow = tmp_path / "kwargs_marker.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        "      - run: |\n"
        "          pytest tests/ -m \"regression and device(serial='1')\"\n"
    )
    violations = check_marker_expression(workflow)
    assert len(violations) == 1


def test_deeply_nested_expression_is_unsafe_not_a_crash(tmp_path):
    """F5: `Expression.compile()` raises `RecursionError`, not `SyntaxError`,
    on a very long expression -- only `SyntaxError` was caught, so this
    crashed the gate instead of returning the documented clean unsafe
    verdict."""
    long_expr = " or ".join(["regression"] * 5000)
    workflow = tmp_path / "deeply_nested.yml"
    workflow.write_text(
        "jobs:\n"
        "  unit:\n"
        "    steps:\n"
        f'      - run: pytest tests/ -m "{long_expr}"\n'
    )
    violations = check_marker_expression(workflow)
    assert len(violations) == 1


def test_non_dict_job_value_does_not_crash(tmp_path):
    """F6: `_iter_run_blocks` lacked the `isinstance(job, dict)` guard its
    sibling `_iter_env_blocks` already has -- a malformed or YAML-anchor-
    collapsed job value that isn't a mapping must be skipped, not crash the
    gate."""
    workflow = tmp_path / "non_dict_job.yml"
    workflow.write_text("jobs:\n  unit: null\n")
    assert check_marker_expression(workflow) == []

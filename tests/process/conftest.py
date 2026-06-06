"""Shared constants, helpers, and fixtures for tests/process/ contract tests.

All tests in this package are pure filesystem operations — no src/ import,
no live services, no LLM calls.  Pattern: DAG-integrity style (BP-017).

Path anchoring: REPO_ROOT is derived from this file's location so it is
CWD-independent and safe in CI (BP-017 §10).
"""

from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

# tests/process/conftest.py  →  .parent = tests/process/
#                              .parent = tests/
#                              .parent = pov-work/  (repo root)
REPO_ROOT = Path(__file__).parent.parent.parent

WORKFLOWS_ROOT = REPO_ROOT / "_ai-memory/pov/workflows"
MODEL_DISPATCH_ROOT = REPO_ROOT / "_ai-memory/pov/skills/aim-model-dispatch/workflows"
SKILLS_ROOT = (
    REPO_ROOT / "_ai-memory/pov/skills"
)  # pov skills (aim-agent-dispatch, aim-agent-lifecycle, …)
CORE_SKILLS_ROOT = (
    REPO_ROOT / "_ai-memory/skills"
)  # core skills (aim-best-practices-researcher, …)

# Placeholder → absolute-path substitutions used in step frontmatter refs.
_PLACEHOLDERS = {
    "{workflows_path}": str(WORKFLOWS_ROOT),
    "{skills_path}": str(SKILLS_ROOT),
    "{project-root}": str(REPO_ROOT),
}

# ---------------------------------------------------------------------------
# Exempt set — workflows with no step chain (inline or reference docs).
#
#   claude-native : reference doc (type: reference), no firstStep key.
#   session/status: single-step inline workflow (firstStep: null).
#
# Both are skipped for firstStep-presence and chain-walk assertions only.
# name/description/h2-section assertions still run for both.
# ---------------------------------------------------------------------------
FIRSTEP_EXEMPT = frozenset(
    [
        (MODEL_DISPATCH_ROOT / "claude-native/workflow.md").resolve(),
        (WORKFLOWS_ROOT / "session/status/workflow.md").resolve(),
    ]
)


# ---------------------------------------------------------------------------
# Core helpers (plain functions — available at parametrize collection time)
# ---------------------------------------------------------------------------


def parse_frontmatter(path: Path) -> dict:
    """Return the YAML frontmatter dict from a markdown file, or {} if none."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


def walk_step_chain(workflow_md: Path) -> list:
    """Walk firstStep→nextStepFile chain from workflow_md.

    Returns the list of visited step Paths.  Each nextStepFile is resolved
    relative to the *step file's* parent — not the workflow root (BP-017 §12).
    Raises AssertionError on dangling reference (file does not exist).
    Returns [] when firstStep is absent or null.

    Cycles: some workflows deliberately loop (e.g. cycles/review-cycle, which
    loops step-03→04→05→03 with an exitStepFile exit path controlled by prose
    logic).  A revisited step terminates the walk gracefully — the contract is
    that every *referenced* file exists, not that the chain is acyclic.
    """
    fm = parse_frontmatter(workflow_md)
    first = fm.get("firstStep")
    if not first:
        return []

    visited: list = []
    seen: set = set()
    next_path = (workflow_md.parent / first).resolve()

    while next_path:
        assert (
            next_path.exists()
        ), f"Dangling step reference: {next_path}  (from {workflow_md})"
        if next_path in seen:
            break  # intentional loop — all links already verified; stop walking
        seen.add(next_path)
        visited.append(next_path)

        step_fm = parse_frontmatter(next_path)
        ref = step_fm.get("nextStepFile")
        if not ref:
            break
        next_path = (next_path.parent / ref).resolve()

    return visited


def resolve_template_ref(ref: str, step_path: Path) -> Path:
    """Resolve a frontmatter template/path ref to an absolute Path.

    Substitutes {workflows_path}, {skills_path}, {project-root} placeholders,
    then resolves relative refs against the step file's parent directory.
    """
    raw = str(ref)
    for placeholder, actual in _PLACEHOLDERS.items():
        raw = raw.replace(placeholder, actual)
    p = Path(raw)
    if p.is_absolute():
        return p.resolve()
    return (step_path.parent / raw).resolve()


# ---------------------------------------------------------------------------
# Discovery functions (called at module level inside test files for parametrize)
# ---------------------------------------------------------------------------


def _all_workflow_mds() -> list:
    """All workflow.md files from both workflow roots, sorted."""
    return sorted(
        list(WORKFLOWS_ROOT.rglob("workflow.md"))
        + list(MODEL_DISPATCH_ROOT.rglob("workflow.md"))
    )


def _all_step_mds() -> list:
    """All step*.md files from both workflow roots, sorted."""
    return sorted(
        list(WORKFLOWS_ROOT.rglob("step*.md"))
        + list(MODEL_DISPATCH_ROOT.rglob("step*.md"))
    )


def _wf_id(p: Path) -> str:
    """Human-readable pytest parametrize ID for a workflow.md path."""
    try:
        return str(p.relative_to(WORKFLOWS_ROOT))
    except ValueError:
        return "model-dispatch/" + str(p.relative_to(MODEL_DISPATCH_ROOT))


def _step_id(p: Path) -> str:
    """Human-readable pytest parametrize ID for a step file path."""
    try:
        return str(p.relative_to(WORKFLOWS_ROOT))
    except ValueError:
        return "model-dispatch/" + str(p.relative_to(MODEL_DISPATCH_ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def workflows_root() -> Path:
    """Session-scoped fixture: WORKFLOWS_ROOT (Section A root)."""
    assert WORKFLOWS_ROOT.is_dir(), f"WORKFLOWS_ROOT not found: {WORKFLOWS_ROOT}"
    return WORKFLOWS_ROOT

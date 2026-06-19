"""Complement tests for the extracted aim-parzival-bootstrap script (TD-590 slice).

The bootstrap logic moved out of the SKILL.md inline block into a standalone,
unit-testable ``bootstrap.py`` (BUG-314). These tests assert the extraction
contract WITHOUT duplicating tests/unit/test_parzival_bootstrap.py (which covers
the library function ``retrieve_bootstrap_context``):

- the read path now resolves scope through the shared ``resolve_project_id``;
- the SKILL.md is thinned to an instruction + script path (no inline program);
- ``main()`` runs and degrades gracefully through the extracted code path.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SKILL_DIR = _REPO / "_ai-memory" / "pov" / "skills" / "aim-parzival-bootstrap"
_BOOTSTRAP_PY = _SKILL_DIR / "bootstrap.py"
_SKILL_MD = _SKILL_DIR / "SKILL.md"


def test_skill_md_is_thinned_and_references_script():
    text = _SKILL_MD.read_text(encoding="utf-8")
    assert "bootstrap.py" in text, "thin SKILL.md must reference the extracted script"
    # The former 300-line inline ```python program must be gone.
    assert "```python" not in text, "SKILL.md still embeds an inline python program"


def test_bootstrap_script_routes_through_shared_resolver():
    src = _BOOTSTRAP_PY.read_text(encoding="utf-8")
    assert "resolve_project_id" in src, "read path must use the shared resolver"
    assert (
        "import detect_project" not in src
    ), "read path must not re-import detect_project directly"


def _load_bootstrap_module():
    spec = importlib.util.spec_from_file_location(
        "_bootstrap_under_test", _BOOTSTRAP_PY
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inject_fake_memory(monkeypatch, resolve_spy: MagicMock) -> None:
    fake_config = MagicMock()
    fake_config.parzival_enabled = True
    fake_config.bootstrap_token_budget = 1000
    fake_config.handoff_ceiling_tokens = 500

    cfg_mod = types.ModuleType("memory.config")
    cfg_mod.MemoryConfig = MagicMock(return_value=fake_config)

    injection_mod = types.ModuleType("memory.injection")
    injection_mod.retrieve_bootstrap_context = MagicMock(return_value=([], {}))
    injection_mod.select_results_greedy = MagicMock(return_value=([], 0, {}))
    injection_mod.format_injection_output = MagicMock(return_value="")
    injection_mod.init_session_state = MagicMock()
    injection_mod.log_injection_event = MagicMock()

    project_mod = types.ModuleType("memory.project")
    project_mod.resolve_project_id = resolve_spy

    search_mod = types.ModuleType("memory.search")
    search_mod.MemorySearch = MagicMock()

    qdrant_mod = types.ModuleType("memory.qdrant_client")
    qdrant_mod.QdrantUnavailable = type("QdrantUnavailable", (Exception,), {})

    metrics_mod = types.ModuleType("memory.metrics_push")
    metrics_mod.push_skill_metrics_async = MagicMock()
    trace_mod = types.ModuleType("memory.trace_buffer")
    trace_mod.emit_trace_event = MagicMock()

    for name, mod in [
        ("memory.config", cfg_mod),
        ("memory.injection", injection_mod),
        ("memory.project", project_mod),
        ("memory.search", search_mod),
        ("memory.qdrant_client", qdrant_mod),
        ("memory.metrics_push", metrics_mod),
        ("memory.trace_buffer", trace_mod),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)


def test_main_resolves_scope_and_runs(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    resolve_spy = MagicMock(return_value="resolved-project")
    _inject_fake_memory(monkeypatch, resolve_spy)

    module = _load_bootstrap_module()
    rc = module.main()

    assert rc == 0
    resolve_spy.assert_called_once()  # read path resolved scope via the shared helper
    out = capsys.readouterr().out
    assert "Cross-Session Memory (Parzival Bootstrap)" in out
    assert "No cross-session memories found" in out


@pytest.mark.parametrize("enabled", [False])
def test_main_respects_parzival_disabled(monkeypatch, capsys, tmp_path, enabled):
    monkeypatch.chdir(tmp_path)
    resolve_spy = MagicMock(return_value="resolved-project")
    _inject_fake_memory(monkeypatch, resolve_spy)
    sys.modules["memory.config"].MemoryConfig.return_value.parzival_enabled = enabled

    module = _load_bootstrap_module()
    rc = module.main()

    assert rc == 0
    out = capsys.readouterr().out
    assert "Parzival is not enabled" in out


def test_output_has_no_github_or_sanctum_sections(monkeypatch, capsys, tmp_path):
    """A1 contract: bootstrap output never contains GitHub Activity or sanctum LORE/BOND.

    Verifies the L4 GitHub layer and Tier-B sanctum prepend are removed.
    Also confirms L1/L2/L3 sections ARE emitted when matching results are present.
    """
    monkeypatch.chdir(tmp_path)
    resolve_spy = MagicMock(return_value="resolved-project")
    _inject_fake_memory(monkeypatch, resolve_spy)

    # Supply one result per kept layer (handoff=L1, decision=L2, insight=L3)
    # plus one github_ result to confirm it does NOT emit a GitHub section.
    fake_results = [
        {
            "id": "h1",
            "type": "agent_handoff",
            "content": "Last handoff content.",
            "score": 0.9,
        },
        {"id": "d1", "type": "decision", "content": "A recent decision.", "score": 0.8},
        {"id": "i1", "type": "agent_insight", "content": "An insight.", "score": 0.7},
        {"id": "g1", "type": "github_pr", "content": "PR #99 merged.", "score": 0.6},
    ]
    sys.modules["memory.injection"].retrieve_bootstrap_context.return_value = (
        fake_results,
        {},
    )
    sys.modules["memory.injection"].select_results_greedy.return_value = (
        fake_results,
        50,
        {},
    )
    sys.modules["memory.injection"].format_injection_output.return_value = ""

    module = _load_bootstrap_module()
    rc = module.main()

    assert rc == 0
    out = capsys.readouterr().out

    # L1/L2/L3 sections must be present
    assert "### Last Handoff" in out, "L1 handoff section must be present"
    assert "### Recent Decisions" in out, "L2 decisions section must be present"
    assert "### Insights" in out, "L3 insights section must be present"

    # GitHub Activity section must NOT be present
    assert "### GitHub Activity" not in out, "L4 GitHub section must have been removed"

    # Sanctum LORE/BOND prepend must NOT be present
    assert (
        "## Sanctum — LORE" not in out
    ), "sanctum LORE section must not appear in bootstrap output"
    assert (
        "## Sanctum — BOND" not in out
    ), "sanctum BOND section must not appear in bootstrap output"

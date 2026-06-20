"""PLAN-028 P2-2 Phase B (BP-164) — score-gap filter LIVE-SKILL-PATH regression.

Exercises the score-gap relevance filter through the PRODUCTION injection
consumption path — the real ``context_injection_tier2.py`` UserPromptSubmit hook
``main()`` — not ``select_results_greedy`` in isolation. That isolation gap is
exactly how BUG-301 escaped to PM #295: a filter validated only on the synthesized
internal function can regress in how the hook *wires* it (threshold not passed,
freshness/gating interaction, formatting) while the unit test stays green.

The hook's consumption path is driven over mocked I/O boundaries (config / qdrant
client / search results / routing) so the genuine route → search → freshness →
gate → ``select_results_greedy(score_gap_threshold=config.injection_score_gap_threshold)``
→ ``format_injection_output`` → ``additionalContext`` chain runs end-to-end. The
fixtures are production-shaped (~150-token handoff/decision/session bodies),
not toy 1-line strings, so the assertions reflect real injected context.

Coverage:
- A near-boundary band candidate (relative ratio below the 0.7 default) is dropped
  from the FINAL injected context — and recorded as a ``score_gap`` reject in the
  audit log the live path writes.
- The live path actually CONSUMES ``config.injection_score_gap_threshold``: lowering
  it to 0.6 keeps the same candidate. A wiring regression that ignores or hardcodes
  the threshold breaks one of the two directions.

PM #346 boundary-sample verdict confirmed 0.7 is correct; this test pins the live
behavior at that value (and its config-sensitivity) so it cannot silently regress.
"""

import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from memory.config import COLLECTION_DISCUSSIONS
from memory.injection import InjectionSessionState, RouteTarget

# Unique sentinels embedded in each candidate body so presence/absence in the
# formatted injected context is unambiguous (format_injection_output emits full
# content verbatim).
KEEP_TOP = "ZZKEEPTOPZZ"
KEEP_MID = "ZZKEEPMIDZZ"
GAP_DROP = "ZZGAPDROPZZ"
# Discriminating candidate: kept by the RELATIVE filter at 0.7 but dropped by a
# flat-threshold regression — see TestScoreGapLiveSkillPath and _result_set().
BAND_KEEP = "ZZBANDKEEPZZ"

_HOOK_PATH = (
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "hooks"
    / "scripts"
    / "context_injection_tier2.py"
)


@pytest.fixture(scope="module")
def hook_module():
    spec = importlib.util.spec_from_file_location("ci_tier2_score_gap", _HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _silence_observability(monkeypatch):
    # The reject counter and trace buffer fork subprocesses / hit the network on
    # the hot path; neutralize them so the test exercises pure decision flow.
    monkeypatch.setattr("memory.injection.emit_trace_event", None, raising=False)
    import memory.metrics_push as _mpush

    monkeypatch.setattr(
        _mpush, "push_retrieval_reject_metric_async", lambda *a, **k: None
    )


class _FakeSearch:
    """Stand-in for MemorySearch: returns a fixed production-shaped result set."""

    def __init__(self, results):
        self._results = results
        self.embedding_client = SimpleNamespace(embed=lambda prompts: [[0.1] * 768])

    def search(self, **kwargs):
        return [dict(r) for r in self._results]

    def close(self):
        pass


def _prod_body(marker: str, topic: str) -> str:
    """A realistic-size (~150-token) discussions-class body carrying a marker.

    Mirrors the shape of a stored agent_handoff / decision: a lead sentence, the
    marker, then several clauses of project prose — far larger than a toy fixture
    so the budget/selection path behaves as it does in production.
    """
    return (
        f"Decision: {topic}. Marker {marker}. "
        "The tier-2 ambient injection path routes the user prompt to candidate "
        "collections, runs hybrid RRF+decay retrieval, applies the code-patterns "
        "freshness penalty, and then performs greedy budget fill with the score-gap "
        "relevance filter so that low-relevance tail candidates do not dilute the "
        "injected context window. Per-source budget ledgers and per-drop reject "
        "records are written to the audit log for observability and tuning. This "
        "body is intentionally sized to resemble a real handoff or decision memory "
        "rather than a one-line synthetic fixture, so that token accounting, greedy "
        "selection ordering, and the score-gap cutoff all behave as they do against "
        "the live store during a genuine UserPromptSubmit turn."
    )


def _result_set():
    """best_score (highest semantic <1.0) = 0.95 → keep cutoff = 0.95 * threshold.

    - KEEP_TOP   score 0.95  ratio 1.000  → always kept
    - KEEP_MID   score 0.72  ratio 0.758  → kept at 0.7 (above cutoff 0.665)
    - BAND_KEEP  score 0.68  ratio 0.716  → kept at 0.7 under the RELATIVE filter
                                            (0.68 >= 0.95*0.7 = 0.665) but DROPPED
                                            by a flat-0.7 regression (0.68 < 0.70).
                                            This is the only candidate whose
                                            keep/drop outcome differs between the
                                            relative (best_score * threshold) and a
                                            flat (threshold) filter, so it is what
                                            pins the relative multiplier the test
                                            documents.
    - GAP_DROP   score 0.62  ratio 0.653  → dropped at 0.7 (below 0.665),
                                            kept at 0.6 (above 0.57)
    raw_score 0.88 (> floor 0.76) on all so the BUG-319 absolute gate passes and
    injection proceeds; score-gap is the only thing that can drop GAP_DROP.
    """
    return [
        {
            "id": "keep-top",
            "content": _prod_body(KEEP_TOP, "score-gap filter confirmed at 0.7"),
            "score": 0.95,
            "raw_score": 0.88,
            "type": "decision",
            "collection": COLLECTION_DISCUSSIONS,
        },
        {
            "id": "keep-mid",
            "content": _prod_body(KEEP_MID, "greedy fill budget ledger"),
            "score": 0.72,
            "raw_score": 0.88,
            "type": "agent_handoff",
            "collection": COLLECTION_DISCUSSIONS,
        },
        {
            "id": "band-keep",
            "content": _prod_body(BAND_KEEP, "relative-vs-flat discriminating band"),
            "score": 0.68,
            "raw_score": 0.88,
            "type": "decision",
            "collection": COLLECTION_DISCUSSIONS,
        },
        {
            "id": "gap-drop",
            "content": _prod_body(GAP_DROP, "near-boundary tail candidate"),
            "score": 0.62,
            "raw_score": 0.88,
            "type": "session",
            "collection": COLLECTION_DISCUSSIONS,
        },
    ]


def _run_hook(
    mod, monkeypatch, capsys, tmp_path, *, results, gap_threshold, session_id
):
    """Drive the real hook main() over mocked boundaries; return additionalContext.

    Budget is set well above the total candidate size so the ONLY reason a
    candidate is absent is the score-gap filter (never budget_exceeded).
    """
    cfg = SimpleNamespace(
        injection_enabled=True,
        injection_absolute_gate_enabled=True,
        injection_absolute_floor=0.76,
        injection_margin_min=0.0,
        injection_freshness_max_age_days=0,
        injection_drift_suppressor_threshold=0.5,
        injection_hard_floor=0.30,
        injection_threshold_conventions=0.6,
        injection_threshold_code_patterns=0.6,
        injection_threshold_discussions=0.6,
        injection_confidence_threshold=0.6,
        max_retrievals=10,
        injection_score_gap_threshold=gap_threshold,
        injection_budget_floor=5000,
        injection_budget_ceiling=5000,
        injection_quality_weight=0.5,
        injection_density_weight=0.3,
        injection_drift_weight=0.2,
        audit_dir=tmp_path,
        get_freshness_penalty=lambda fs: 1.0,
    )
    monkeypatch.setattr(mod, "get_config", lambda: cfg)
    monkeypatch.setattr(mod, "get_qdrant_client", lambda c: object())
    monkeypatch.setattr(mod, "check_qdrant_health", lambda c: True)
    monkeypatch.setattr(mod, "resolve_project_id", lambda cwd: "proj")
    monkeypatch.setattr(mod, "MemorySearch", lambda c: _FakeSearch(results))
    monkeypatch.setattr(
        mod, "route_collections", lambda p: [RouteTarget(COLLECTION_DISCUSSIONS)]
    )
    monkeypatch.setattr(mod, "emit_trace_event", None, raising=False)
    monkeypatch.setattr(mod, "push_hook_metrics_async", lambda **k: None, raising=False)

    # Hermetic session state: production InjectionSessionState._state_path returns a
    # shared /tmp/ai-memory-{id}-injection-state.json that a stale file from prior
    # local runs or a parallel test could poison. Redirect it under the per-test
    # tmp_path so the excluded_ids dedup state is isolated and this test never reads
    # or writes the shared /tmp location.
    monkeypatch.setattr(
        InjectionSessionState,
        "_state_path",
        staticmethod(lambda sid: tmp_path / f"injection-state-{sid}.json"),
    )

    stdin_payload = json.dumps(
        {
            "prompt": "what did we decide about the score-gap relevance filter",
            "session_id": session_id,
            "cwd": str(tmp_path),
        }
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin_payload))

    rc = mod.main()
    # main() returns 0 by graceful-degradation design even when nothing is
    # injected, so rc is non-discriminating; the content/audit assertions in
    # each test are the real guard. Kept only as a smoke check that main()
    # completed without raising.
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    return payload["hookSpecificOutput"]["additionalContext"]


def _audit_rejects(tmp_path):
    """Return the rejects[] list from the single injection-log entry written."""
    log_path = tmp_path / "logs" / "injection-log.jsonl"
    lines = [ln for ln in log_path.read_text().splitlines() if ln.strip()]
    assert lines, "live path must have written an injection-log entry"
    return json.loads(lines[-1])["rejects"]


class TestScoreGapLiveSkillPath:
    def test_tail_candidate_dropped_relative_band_kept_at_default_threshold(
        self, hook_module, monkeypatch, capsys, tmp_path
    ):
        """At the 0.7 default the near-boundary candidate (ratio 0.653) is absent
        from the injected context the hook hands to Claude, and is attributed as a
        ``score_gap`` reject in the audit log — both observed through the live path,
        not the isolated select_results_greedy call."""
        ctx = _run_hook(
            hook_module,
            monkeypatch,
            capsys,
            tmp_path,
            results=_result_set(),
            gap_threshold=0.7,
            session_id="plan028-p22-gap-default",
        )
        assert "<retrieved_context>" in ctx  # injection proceeded
        assert KEEP_TOP in ctx
        assert KEEP_MID in ctx
        # The band candidate (score 0.68, ratio 0.716) is KEPT by the relative
        # filter (0.68 >= 0.95*0.7 = 0.665). A regression that swapped the
        # relative cutoff for a flat one (result_score < threshold) would drop it
        # (0.68 < 0.70) and this assertion would fail — this is what actually pins
        # the relative multiplier rather than a flat threshold.
        assert BAND_KEEP in ctx
        assert GAP_DROP not in ctx  # dropped by the score-gap filter

        rejects = _audit_rejects(tmp_path)
        gap = [r for r in rejects if r["reason"] == "score_gap"]
        assert gap, "the dropped candidate must be recorded as a score_gap reject"
        # Precise attribution: the sole score_gap reject is the GAP_DROP candidate.
        # The reject record the live path writes carries no id field, so it is
        # identified by its unique (type, score) signature — type "session" and
        # score 0.62 belong only to the "gap-drop" candidate in _result_set().
        assert len(gap) == 1
        assert gap[0]["type"] == "session"
        assert gap[0]["score"] == 0.62

    def test_live_path_consumes_configured_threshold(
        self, hook_module, monkeypatch, capsys, tmp_path
    ):
        """Lowering ``injection_score_gap_threshold`` to 0.6 keeps the same
        candidate (ratio 0.653 > 0.6). This proves the hook threads the CONFIG
        value into the production filter — a regression that ignores or hardcodes
        the threshold would fail this together with the default-threshold case
        above."""
        ctx = _run_hook(
            hook_module,
            monkeypatch,
            capsys,
            tmp_path,
            results=_result_set(),
            gap_threshold=0.6,
            session_id="plan028-p22-gap-lowered",
        )
        assert "<retrieved_context>" in ctx
        assert KEEP_TOP in ctx
        assert KEEP_MID in ctx
        assert BAND_KEEP in ctx  # well above the lowered cutoff → kept
        assert GAP_DROP in ctx  # now above the lowered cutoff → kept

        rejects = _audit_rejects(tmp_path)
        assert not [
            r for r in rejects if r["reason"] == "score_gap"
        ], "no score_gap reject expected once the candidate clears the lowered cutoff"

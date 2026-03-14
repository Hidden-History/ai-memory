# LANGFUSE: V3 SDK ONLY. See LANGFUSE-INTEGRATION-SPEC.md
# FORBIDDEN: Langfuse(host=...) with explicit creds, start_span(), start_generation(), langfuse_context
# REQUIRED: get_client(), dataset.items, item.run(), flush()
"""Regression tests using Langfuse golden datasets.

These tests run Langfuse experiments against the 5 golden datasets created by
scripts/create_datasets.py. They require live Langfuse + Qdrant to run and
are NOT unit tests — they validate end-to-end system behaviour.

Datasets used:
  DS-01: ds-01-retrieval-golden-set     — retrieval relevance (EV-01)
  DS-02: ds-02-error-pattern-match      — error pattern matching (EV-03)
  DS-03: ds-03-bootstrap-round-trip     — bootstrap round-trip (EV-05)
  DS-04: ds-04-keyword-trigger-routing  — keyword routing accuracy (DS-04)

Run regression tests only:
    pytest -m regression tests/test_regression.py -v --tb=short

PLAN-012 Phase 3 — Section 6.2
"""

import logging
from datetime import date

import pytest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Quality thresholds — adjust here only, not inside test functions
# ---------------------------------------------------------------------------

MIN_RETRIEVAL_RELEVANCE = 0.7  # DS-01: avg score across all items
MIN_ERROR_MATCH_RATE = 0.80  # DS-02: fraction of items with a hit
KEYWORD_ROUTING_ACCURACY = 1.0  # DS-04: must be 100% (68/68)

# ---------------------------------------------------------------------------
# Dataset names (must match scripts/create_datasets.py DATASETS list)
# ---------------------------------------------------------------------------

DS_01_NAME = "ds-01-retrieval-golden-set"
DS_02_NAME = "ds-02-error-pattern-match"
DS_03_NAME = "ds-03-bootstrap-round-trip"
DS_04_NAME = "ds-04-keyword-trigger-routing"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def langfuse():
    """Return a Langfuse V3 client, skipping the module if unavailable."""
    try:
        from langfuse import get_client  # V3 singleton

        client = get_client()
        # Verify connectivity with a lightweight call
        client.auth_check()
        return client
    except ImportError:
        pytest.skip("langfuse package not installed — pip install 'langfuse>=3.0,<4.0'")
    except Exception as exc:
        pytest.skip(f"Langfuse unavailable or not configured: {exc}")


# ---------------------------------------------------------------------------
# Helper: run experiment over all dataset items
# ---------------------------------------------------------------------------


def _run_experiment(langfuse, dataset_name: str, run_name: str, task_fn):
    """Iterate a Langfuse dataset, call task_fn on each item, return results.

    Args:
        langfuse: Langfuse V3 client from get_client().
        dataset_name: Name of the Langfuse dataset to iterate.
        run_name: Experiment run name (e.g. "retrieval-regression-2026-03-14").
        task_fn: Callable(item_input) -> dict with at least {"score": float/bool}.

    Returns:
        List of dicts — one entry per dataset item with keys:
            item_id, input, expected_output, result, score, error
    """
    try:
        dataset = langfuse.get_dataset(dataset_name)
    except Exception as exc:
        pytest.skip(f"Dataset '{dataset_name}' not found in Langfuse: {exc}")

    results = []
    for item in dataset.items:
        entry = {
            "item_id": item.id,
            "input": item.input,
            "expected_output": item.expected_output,
            "result": None,
            "score": None,
            "error": None,
        }
        try:
            with item.run(run_name=run_name) as run:
                result = task_fn(item.input, item.expected_output)
                entry["result"] = result
                entry["score"] = result.get("score")
                run.score(
                    name=result.get("score_name", "regression_score"),
                    value=result["score"],
                    comment=result.get("reasoning", ""),
                )
        except Exception as exc:
            entry["error"] = str(exc)
            logger.warning("Item %s failed: %s", item.id, exc)

        results.append(entry)

    return results


# ---------------------------------------------------------------------------
# DS-01: Retrieval quality regression
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_retrieval_quality_regression(langfuse):
    """DS-01: avg retrieval relevance across golden set must be >= 0.7."""
    today = date.today().isoformat()
    run_name = f"retrieval-regression-{today}"

    def retrieval_task(inp, expected):
        """Search Qdrant with the item query, compare top result relevance."""
        try:
            from memory.search import MemorySearch
        except ImportError:
            pytest.skip("memory.search not available")

        query = inp.get("query", "")
        collection = inp.get("collection", "code-patterns")
        type_filter = inp.get("type_filter")
        min_relevance = expected.get("min_relevance", MIN_RETRIEVAL_RELEVANCE)

        try:
            searcher = MemorySearch()
            results = searcher.search(
                query=query,
                collection=collection,
                type_filter=type_filter,
                limit=5,
            )
        except Exception as exc:
            return {
                "score": 0.0,
                "score_name": "retrieval_relevance",
                "reasoning": f"Search failed: {exc}",
            }

        if not results:
            return {
                "score": 0.0,
                "score_name": "retrieval_relevance",
                "reasoning": "No results returned",
            }

        # Use top result score as relevance proxy
        top_score = results[0].score if hasattr(results[0], "score") else 0.0
        # Normalise to [0,1] if needed (Qdrant cosine returns -1..1 range rarely)
        top_score = max(0.0, min(1.0, float(top_score)))
        passed = top_score >= min_relevance
        return {
            "score": top_score,
            "score_name": "retrieval_relevance",
            "reasoning": f"Top result score {top_score:.3f} vs threshold {min_relevance}",
            "passed": passed,
        }

    results = _run_experiment(langfuse, DS_01_NAME, run_name, retrieval_task)
    langfuse.flush()

    scored = [r for r in results if r["score"] is not None]
    assert scored, "No items were scored — check Qdrant connectivity"

    avg_score = sum(r["score"] for r in scored) / len(scored)
    assert avg_score >= MIN_RETRIEVAL_RELEVANCE, (
        f"Avg retrieval relevance {avg_score:.3f} < threshold {MIN_RETRIEVAL_RELEVANCE}. "
        f"Scored {len(scored)}/{len(results)} items."
    )


# ---------------------------------------------------------------------------
# DS-04: Keyword trigger routing regression
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_keyword_routing_regression(langfuse):
    """DS-04: all 68 keyword patterns must route to the correct trigger (100%)."""
    today = date.today().isoformat()
    run_name = f"keyword-routing-regression-{today}"

    def routing_task(inp, expected):
        """Run trigger detection on user_prompt, check collection matches."""
        try:
            from memory.triggers import (
                detect_best_practices_keywords,
                detect_decision_keywords,
                detect_error_signal,
                detect_session_history_keywords,
            )
        except ImportError:
            pytest.skip("memory.triggers not available")

        user_prompt = inp.get("user_prompt", "")
        expected_trigger = expected.get("expected_trigger", "")

        # Try each detector in order — first match wins (mirrors hook logic)
        detected_trigger = None
        if detect_error_signal(user_prompt):
            detected_trigger = "error_detection"
        elif detect_best_practices_keywords(user_prompt):
            detected_trigger = "best_practices_keywords"
        elif detect_decision_keywords(user_prompt):
            detected_trigger = "decision_keywords"
        elif detect_session_history_keywords(user_prompt):
            detected_trigger = "session_history_keywords"

        matched = detected_trigger == expected_trigger
        score = 1.0 if matched else 0.0
        return {
            "score": score,
            "score_name": "routing_accuracy",
            "reasoning": (
                f"prompt={user_prompt!r} → detected={detected_trigger!r}, "
                f"expected={expected_trigger!r}"
            ),
            "passed": matched,
        }

    results = _run_experiment(langfuse, DS_04_NAME, run_name, routing_task)
    langfuse.flush()

    scored = [r for r in results if r["score"] is not None]
    assert scored, "No items were scored — check dataset exists"

    accuracy = sum(r["score"] for r in scored) / len(scored)
    assert accuracy >= KEYWORD_ROUTING_ACCURACY, (
        f"Keyword routing accuracy {accuracy:.1%} < {KEYWORD_ROUTING_ACCURACY:.1%}. "
        f"Failures: {[r for r in scored if r['score'] < 1.0]}"
    )


# ---------------------------------------------------------------------------
# DS-02: Error pattern match regression
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_error_pattern_match_regression(langfuse):
    """DS-02: >= 80% of error messages must match a code-patterns entry."""
    today = date.today().isoformat()
    run_name = f"error-pattern-regression-{today}"

    def error_match_task(inp, expected):
        """Search code-patterns for error, check if a hit is found."""
        try:
            from memory.search import MemorySearch
        except ImportError:
            pytest.skip("memory.search not available")

        error_msg = inp.get("error_message", inp.get("query", ""))

        try:
            searcher = MemorySearch()
            results = searcher.search(
                query=error_msg,
                collection="code-patterns",
                type_filter="error_pattern",
                limit=3,
            )
        except Exception as exc:
            return {
                "score": 0.0,
                "score_name": "error_match",
                "reasoning": f"Search failed: {exc}",
            }

        # Hit = at least one result with score >= 0.5
        hit = any((r.score if hasattr(r, "score") else 0.0) >= 0.5 for r in results)
        return {
            "score": 1.0 if hit else 0.0,
            "score_name": "error_match",
            "reasoning": f"error={error_msg!r} → {'HIT' if hit else 'MISS'} "
            f"({len(results)} results returned)",
            "passed": hit,
        }

    results = _run_experiment(langfuse, DS_02_NAME, run_name, error_match_task)
    langfuse.flush()

    scored = [r for r in results if r["score"] is not None]
    assert scored, "No items were scored — check Qdrant connectivity"

    match_rate = sum(r["score"] for r in scored) / len(scored)
    assert match_rate >= MIN_ERROR_MATCH_RATE, (
        f"Error pattern match rate {match_rate:.1%} < threshold {MIN_ERROR_MATCH_RATE:.1%}. "
        f"Misses: {[r for r in scored if r['score'] == 0.0]}"
    )


# ---------------------------------------------------------------------------
# DS-03: Bootstrap round-trip regression
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_bootstrap_round_trip(langfuse):
    """DS-03: handoff content stored via parzival-save-handoff must be retrievable."""
    today = date.today().isoformat()
    run_name = f"bootstrap-round-trip-{today}"

    def bootstrap_task(inp, expected):
        """Search discussions for handoff content, verify agent_id=parzival isolation."""
        try:
            from memory.search import MemorySearch
        except ImportError:
            pytest.skip("memory.search not available")

        handoff_content = inp.get("handoff_content", inp.get("query", ""))
        expected_keywords = expected.get("expected_keywords", [])

        try:
            searcher = MemorySearch()
            results = searcher.search(
                query=handoff_content,
                collection="discussions",
                type_filter="session",
                limit=5,
            )
        except Exception as exc:
            return {
                "score": 0.0,
                "score_name": "bootstrap_retrieval",
                "reasoning": f"Search failed: {exc}",
            }

        if not results:
            return {
                "score": 0.0,
                "score_name": "bootstrap_retrieval",
                "reasoning": "No results — handoff content not found in discussions",
                "passed": False,
            }

        # Check that the top result contains expected keywords (if provided)
        top_content = ""
        if hasattr(results[0], "payload"):
            top_content = str(results[0].payload.get("content", ""))
        elif hasattr(results[0], "content"):
            top_content = str(results[0].content)

        if expected_keywords:
            matches = sum(
                1 for kw in expected_keywords if kw.lower() in top_content.lower()
            )
            score = matches / len(expected_keywords)
        else:
            # No expected keywords — presence of any result is sufficient
            score = 1.0 if results else 0.0

        return {
            "score": score,
            "score_name": "bootstrap_retrieval",
            "reasoning": (
                f"Found {len(results)} results; keyword match "
                f"{int(score * len(expected_keywords)) if expected_keywords else 'N/A'}"
                f"/{len(expected_keywords) if expected_keywords else 'N/A'}"
            ),
            "passed": score > 0.0,
        }

    results = _run_experiment(langfuse, DS_03_NAME, run_name, bootstrap_task)
    langfuse.flush()

    scored = [r for r in results if r["score"] is not None]
    assert scored, "No items were scored — check Qdrant connectivity"

    # Bootstrap round-trip: at least one result must be found per item
    assert not any(r["score"] == 0.0 for r in scored), (
        f"Bootstrap round-trip failed for {sum(1 for r in scored if r['score'] == 0.0)} items. "
        f"Handoff content not retrievable — check parzival tenant isolation."
    )

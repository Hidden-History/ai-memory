# LANGFUSE: V3 SDK ONLY. See LANGFUSE-INTEGRATION-SPEC.md
"""Tests for memory.evaluator.runner — EvaluatorRunner core pipeline.

Tests trace filtering, sampling, score attachment, and pagination using
mocked Langfuse client.

Covers:
- Trace-level evaluation path (EV-05, EV-06 style)
- Observation-level evaluation path (EV-01-EV-04 style)
- Cursor-based pagination for observations (BUG-217)
- Page-based pagination for traces
- CATEGORICAL score type (EV-04)
- observation_id in _make_score_id to prevent collisions (BUG-S163)
- Per-evaluator target: routing

PLAN-012 Phase 2 — AC-8
S-16.3
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from memory.evaluator.runner import EvaluatorRunner

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_config(tmp_path) -> Path:
    """Write a minimal evaluator_config.yaml to a tmp directory."""
    config_content = """
evaluator_model:
  provider: ollama
  model_name: gemma3:4b
  temperature: 0.0
  max_tokens: 4096
evaluators_dir: {evaluators_dir}
audit:
  log_file: {audit_log}
""".format(
        evaluators_dir=str(tmp_path / "evaluators"),
        audit_log=str(tmp_path / ".audit" / "evaluations.jsonl"),
    )
    config_file = tmp_path / "evaluator_config.yaml"
    config_file.write_text(config_content)
    (tmp_path / "evaluators").mkdir()
    return config_file


@pytest.fixture()
def runner(minimal_config) -> EvaluatorRunner:
    return EvaluatorRunner(config_path=str(minimal_config))


@pytest.fixture()
def trace_evaluator_yaml(tmp_path, minimal_config) -> dict:
    """Create a trace-level evaluator YAML (EV-05 style)."""
    runner = EvaluatorRunner(config_path=str(minimal_config))
    ev_yaml = {
        "id": "EV-05",
        "name": "bootstrap_quality",
        "score_type": "NUMERIC",
        "target": "trace",
        "filter": {"event_types": ["session_bootstrap"]},
        "sampling_rate": 1.0,
        "prompt_file": "ev05_prompt.md",
    }
    ev_dir = runner.evaluators_dir
    ev_dir.mkdir(parents=True, exist_ok=True)

    ev_file = ev_dir / "ev05_bootstrap_quality.yaml"
    import yaml

    ev_file.write_text(yaml.dump(ev_yaml))

    prompt_file = ev_dir / "ev05_prompt.md"
    prompt_file.write_text("Evaluate this bootstrap session.")

    return ev_yaml


@pytest.fixture()
def observation_evaluator_yaml(tmp_path, minimal_config) -> dict:
    """Create an observation-level evaluator YAML (EV-01 style)."""
    runner = EvaluatorRunner(config_path=str(minimal_config))
    ev_yaml = {
        "id": "EV-01",
        "name": "retrieval_relevance",
        "score_type": "NUMERIC",
        "target": "observation",
        "filter": {"event_types": ["search_query", "context_retrieval"]},
        "sampling_rate": 1.0,
        "prompt_file": "ev01_prompt.md",
    }
    ev_dir = runner.evaluators_dir
    ev_dir.mkdir(parents=True, exist_ok=True)

    ev_file = ev_dir / "ev01_retrieval_relevance.yaml"
    import yaml

    ev_file.write_text(yaml.dump(ev_yaml))

    prompt_file = ev_dir / "ev01_prompt.md"
    prompt_file.write_text("Evaluate this retrieval.")

    return ev_yaml


@pytest.fixture()
def categorical_evaluator_yaml(tmp_path, minimal_config) -> dict:
    """Create a CATEGORICAL observation-level evaluator (EV-04 style)."""
    runner = EvaluatorRunner(config_path=str(minimal_config))
    ev_yaml = {
        "id": "EV-04",
        "name": "classification_accuracy",
        "score_type": "CATEGORICAL",
        "target": "observation",
        "categories": ["correct", "partially_correct", "incorrect"],
        "filter": {"event_types": ["9_classify"]},
        "sampling_rate": 1.0,
        "prompt_file": "ev04_prompt.md",
    }
    ev_dir = runner.evaluators_dir
    ev_dir.mkdir(parents=True, exist_ok=True)

    ev_file = ev_dir / "ev04_classification_accuracy.yaml"
    import yaml

    ev_file.write_text(yaml.dump(ev_yaml))

    prompt_file = ev_dir / "ev04_prompt.md"
    prompt_file.write_text("Evaluate this classification.")

    return ev_yaml


# For backward compat — existing tests use evaluator_yaml for a trace evaluator
@pytest.fixture()
def evaluator_yaml(tmp_path, minimal_config) -> dict:
    """Create a single evaluator YAML in the evaluators directory."""
    runner = EvaluatorRunner(config_path=str(minimal_config))
    ev_yaml = {
        "id": "EV-01",
        "name": "retrieval_relevance",
        "score_type": "NUMERIC",
        "target": "trace",
        "filter": {"tags": ["retrieval"]},
        "sampling_rate": 1.0,
        "prompt_file": "ev01_prompt.md",
    }
    ev_dir = runner.evaluators_dir
    ev_dir.mkdir(parents=True, exist_ok=True)

    ev_file = ev_dir / "ev01_retrieval_relevance.yaml"
    import yaml

    ev_file.write_text(yaml.dump(ev_yaml))

    prompt_file = ev_dir / "ev01_prompt.md"
    prompt_file.write_text(
        "Evaluate this retrieval.\n\nInput: {input}\nOutput: {output}"
    )

    return ev_yaml


def make_mock_trace(
    trace_id: str = "abc123",
    name: str = "search_query",
    tags: list | None = None,
    output: str | None = "Some output",
):
    trace = MagicMock()
    trace.id = trace_id
    trace.name = name
    trace.tags = tags or []
    trace.input = "test input"
    trace.output = output
    trace.metadata = {}
    return trace


def make_mock_observation(
    obs_id: str = "obs001",
    trace_id: str = "trace001",
    name: str = "search_query",
    output: str | None = "retrieved context",
):
    obs = MagicMock()
    obs.id = obs_id
    obs.trace_id = trace_id
    obs.name = name
    obs.input = "query text"
    obs.output = output
    obs.metadata = {}
    return obs


def make_paginated_response(traces: list, total_pages=1):
    """Page-based response for trace.list()."""
    response = MagicMock()
    response.data = traces
    response.meta = MagicMock()
    response.meta.total_pages = total_pages
    return response


def make_observation_response(observations: list, total_pages: int = 1):
    """Page-based response for observations.get_many()."""
    response = MagicMock()
    response.data = observations
    response.meta = MagicMock()
    response.meta.total_pages = total_pages
    return response


# ---------------------------------------------------------------------------
# Tests: _matches_filter
# ---------------------------------------------------------------------------


class TestMatchesFilter:
    def test_empty_filter_matches_all(self, runner):
        trace = make_mock_trace(tags=["anything"])
        assert runner._matches_filter(trace, {}) is True

    def test_tag_filter_passes_when_tag_present(self, runner):
        trace = make_mock_trace(tags=["retrieval", "search"])
        assert runner._matches_filter(trace, {"tags": ["retrieval"]}) is True

    def test_tag_filter_fails_when_no_tag_match(self, runner):
        trace = make_mock_trace(tags=["capture"])
        assert runner._matches_filter(trace, {"tags": ["retrieval"]}) is False

    def test_event_type_filter_passes_when_name_matches(self, runner):
        trace = make_mock_trace(name="9_classify")
        assert runner._matches_filter(trace, {"event_types": ["9_classify"]}) is True

    def test_event_type_filter_fails_when_name_mismatch(self, runner):
        trace = make_mock_trace(name="1_capture")
        assert runner._matches_filter(trace, {"event_types": ["9_classify"]}) is False

    def test_combined_filter_both_must_match(self, runner):
        trace = make_mock_trace(name="9_classify", tags=["classification"])
        assert (
            runner._matches_filter(
                trace, {"tags": ["classification"], "event_types": ["9_classify"]}
            )
            is True
        )

    def test_combined_filter_fails_if_one_misses(self, runner):
        trace = make_mock_trace(name="9_classify", tags=["capture"])
        assert (
            runner._matches_filter(
                trace, {"tags": ["classification"], "event_types": ["9_classify"]}
            )
            is False
        )


# ---------------------------------------------------------------------------
# Tests: _make_score_id
# ---------------------------------------------------------------------------


class TestMakeScoreId:
    def test_deterministic_for_same_inputs(self, runner):
        since = datetime(2026, 3, 13, tzinfo=timezone.utc)
        id1 = runner._make_score_id("trace123", "retrieval_relevance", since)
        id2 = runner._make_score_id("trace123", "retrieval_relevance", since)
        assert id1 == id2

    def test_different_trace_ids_produce_different_scores(self, runner):
        since = datetime(2026, 3, 13, tzinfo=timezone.utc)
        id1 = runner._make_score_id("trace_A", "retrieval_relevance", since)
        id2 = runner._make_score_id("trace_B", "retrieval_relevance", since)
        assert id1 != id2

    def test_different_since_produces_different_id(self, runner):
        since_a = datetime(2026, 3, 12, tzinfo=timezone.utc)
        since_b = datetime(2026, 3, 13, tzinfo=timezone.utc)
        id1 = runner._make_score_id("trace123", "retrieval_relevance", since_a)
        id2 = runner._make_score_id("trace123", "retrieval_relevance", since_b)
        assert id1 != id2

    def test_returns_hex_string(self, runner):
        since = datetime(2026, 3, 13, tzinfo=timezone.utc)
        score_id = runner._make_score_id("trace123", "retrieval_relevance", since)
        assert len(score_id) == 32
        int(score_id, 16)  # Must be valid hex

    def test_matches_expected_md5_without_observation_id(self, runner):
        since = datetime(2026, 3, 13, 0, 0, 0, tzinfo=timezone.utc)
        expected = hashlib.md5(
            f"trace123:retrieval_relevance:{since.isoformat()}".encode()
        ).hexdigest()
        assert (
            runner._make_score_id("trace123", "retrieval_relevance", since) == expected
        )

    def test_observation_id_changes_score_id(self, runner):
        """Two observations from the same trace must get different score IDs (BUG-S163)."""
        since = datetime(2026, 3, 13, tzinfo=timezone.utc)
        id_without = runner._make_score_id("trace123", "retrieval_relevance", since)
        id_with = runner._make_score_id(
            "trace123", "retrieval_relevance", since, observation_id="obs001"
        )
        assert id_without != id_with

    def test_different_observation_ids_produce_different_scores(self, runner):
        """Multiple observations in same trace must get unique score IDs."""
        since = datetime(2026, 3, 13, tzinfo=timezone.utc)
        id1 = runner._make_score_id(
            "trace123", "retrieval_relevance", since, observation_id="obs001"
        )
        id2 = runner._make_score_id(
            "trace123", "retrieval_relevance", since, observation_id="obs002"
        )
        assert id1 != id2

    def test_observation_id_md5_includes_observation_in_seed(self, runner):
        since = datetime(2026, 3, 13, 0, 0, 0, tzinfo=timezone.utc)
        expected = hashlib.md5(
            f"trace123:obs001:retrieval_relevance:{since.isoformat()}".encode()
        ).hexdigest()
        assert (
            runner._make_score_id(
                "trace123", "retrieval_relevance", since, observation_id="obs001"
            )
            == expected
        )


# ---------------------------------------------------------------------------
# Tests: run() — trace-level path (existing behaviour, no regression)
# ---------------------------------------------------------------------------


class TestRunnerRunTracePath:
    def test_run_with_no_evaluators_returns_zero_summary(self, runner):
        """When evaluators_dir is empty, run() returns all-zero summary."""
        mock_langfuse = MagicMock()
        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with patch("memory.evaluator.runner.get_client", return_value=mock_langfuse):
            result = runner.run(since=since)

        assert result == {"fetched": 0, "sampled": 0, "evaluated": 0, "scored": 0}

    def test_run_attaches_score_for_matching_trace(self, runner, evaluator_yaml):
        """Matching trace should get a score attached via create_score()."""
        trace = make_mock_trace(trace_id="trace001", tags=["retrieval"])
        mock_langfuse = MagicMock()
        mock_langfuse.api.trace.list.return_value = make_paginated_response([trace])

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.return_value = {
            "score": 0.9,
            "reasoning": "Very relevant",
        }

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
        ):
            result = runner.run(since=since)

        assert result["evaluated"] == 1
        assert result["scored"] == 1
        mock_langfuse.create_score.assert_called_once()
        call_kwargs = mock_langfuse.create_score.call_args.kwargs
        assert call_kwargs["trace_id"] == "trace001"
        assert call_kwargs["name"] == "retrieval_relevance"
        assert call_kwargs["value"] == 0.9
        # Trace-level score must NOT have observation_id
        assert call_kwargs.get("observation_id") is None

    def test_run_dry_run_does_not_call_create_score(self, runner, evaluator_yaml):
        """dry_run=True should evaluate but NOT call create_score()."""
        trace = make_mock_trace(trace_id="trace002", tags=["retrieval"])
        mock_langfuse = MagicMock()
        mock_langfuse.api.trace.list.return_value = make_paginated_response([trace])

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.return_value = {"score": 0.7, "reasoning": "OK"}

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
        ):
            result = runner.run(since=since, dry_run=True)

        assert result["evaluated"] == 1
        assert result["scored"] == 0
        mock_langfuse.create_score.assert_not_called()

    def test_run_skips_trace_with_no_output(self, runner, evaluator_yaml):
        """Traces with output=None should be skipped (no evaluation)."""
        trace = make_mock_trace(trace_id="trace003", tags=["retrieval"], output=None)
        mock_langfuse = MagicMock()
        mock_langfuse.api.trace.list.return_value = make_paginated_response([trace])

        mock_evaluator_config = MagicMock()
        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
        ):
            result = runner.run(since=since)

        assert result["evaluated"] == 0
        assert (
            result["sampled"] == 0
        )  # R2-F7: sampled not incremented for no-output traces
        mock_evaluator_config.evaluate.assert_not_called()

    def test_run_uses_page_pagination_for_trace_path(self, runner, evaluator_yaml):
        """Trace path must advance page number when more pages are available."""
        trace1 = make_mock_trace(trace_id="trace_p1", tags=["retrieval"])
        trace2 = make_mock_trace(trace_id="trace_p2", tags=["retrieval"])

        mock_langfuse = MagicMock()
        mock_langfuse.api.trace.list.side_effect = [
            make_paginated_response([trace1], total_pages=2),
            make_paginated_response([trace2], total_pages=2),
        ]

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.return_value = {
            "score": 0.8,
            "reasoning": "Fine",
        }

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
        ):
            result = runner.run(since=since)

        assert result["evaluated"] == 2
        # Second call must have used page=2
        second_call_kwargs = mock_langfuse.api.trace.list.call_args_list[1].kwargs
        assert second_call_kwargs.get("page") == 2

    def test_run_calls_flush_after_all_evaluations(self, runner, evaluator_yaml):
        """langfuse.flush() must be called after all evaluations complete."""
        mock_langfuse = MagicMock()
        mock_langfuse.api.trace.list.return_value = make_paginated_response([])

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with patch("memory.evaluator.runner.get_client", return_value=mock_langfuse):
            runner.run(since=since)

        mock_langfuse.flush.assert_called_once()

    def test_run_filters_by_evaluator_id(self, runner, tmp_path):
        """--evaluator EV-05 should only load EV-05 definition."""
        ev_dir = runner.evaluators_dir
        ev_dir.mkdir(parents=True, exist_ok=True)

        import yaml

        ev05 = {
            "id": "EV-05",
            "name": "bootstrap_quality",
            "score_type": "NUMERIC",
            "target": "trace",
            "filter": {},
            "sampling_rate": 1.0,
            "prompt_file": "prompt.md",
        }
        ev06 = {
            "id": "EV-06",
            "name": "session_coherence",
            "score_type": "NUMERIC",
            "target": "trace",
            "filter": {},
            "sampling_rate": 1.0,
            "prompt_file": "prompt.md",
        }
        (ev_dir / "ev05.yaml").write_text(yaml.dump(ev05))
        (ev_dir / "ev06.yaml").write_text(yaml.dump(ev06))
        (ev_dir / "prompt.md").write_text("Evaluate this.")

        mock_langfuse = MagicMock()
        mock_langfuse.api.trace.list.return_value = make_paginated_response([])

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with patch("memory.evaluator.runner.get_client", return_value=mock_langfuse):
            runner.run(evaluator_id="EV-05", since=since)

        # trace.list should have been called once (for EV-05 only)
        assert mock_langfuse.api.trace.list.call_count == 1

    def test_run_appends_to_audit_log(self, runner, evaluator_yaml, tmp_path):
        """Evaluated traces should be written to the JSONL audit log."""
        trace = make_mock_trace(trace_id="audit_trace", tags=["retrieval"])
        mock_langfuse = MagicMock()
        mock_langfuse.api.trace.list.return_value = make_paginated_response([trace])

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.return_value = {
            "score": 0.75,
            "reasoning": "Logged",
        }

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
        ):
            runner.run(since=since)

        assert runner.audit_log_path.exists()
        lines = runner.audit_log_path.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["trace_id"] == "audit_trace"
        assert entry["score"] == 0.75

    def test_run_uses_get_client_not_constructor(self, runner, evaluator_yaml):
        """Must use get_client() — never Langfuse() constructor directly in code."""
        import inspect

        import memory.evaluator.runner as runner_module

        source = inspect.getsource(runner_module)
        assert "get_client" in source
        non_comment_lines = [
            line for line in source.splitlines() if not line.strip().startswith("#")
        ]
        non_comment_source = "\n".join(non_comment_lines)
        assert "Langfuse()" not in non_comment_source


# ---------------------------------------------------------------------------
# Tests: run() — observation-level path (S-16.3)
# ---------------------------------------------------------------------------


class TestRunnerRunObservationPath:
    def test_observation_path_calls_observations_get_many(
        self, runner, observation_evaluator_yaml
    ):
        """Observation target must call observations.get_many(), not trace.list()."""
        obs = make_mock_observation(obs_id="obs001", trace_id="trace001")
        mock_langfuse = MagicMock()
        # Two event_types → two API calls (one per name_filter)
        mock_langfuse.api.observations.get_many.return_value = (
            make_observation_response([obs])
        )

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.return_value = {
            "score": 0.85,
            "reasoning": "Good",
        }

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
        ):
            runner.run(since=since)

        assert mock_langfuse.api.observations.get_many.call_count == 2
        mock_langfuse.api.trace.list.assert_not_called()

    def test_observation_score_includes_observation_id(
        self, runner, observation_evaluator_yaml
    ):
        """create_score() for observation target must include observation_id."""
        obs = make_mock_observation(obs_id="obs_xyz", trace_id="trace_abc")
        mock_langfuse = MagicMock()
        mock_langfuse.api.observations.get_many.return_value = (
            make_observation_response([obs])
        )

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.return_value = {"score": 0.9, "reasoning": ""}

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
        ):
            runner.run(since=since)

        assert mock_langfuse.create_score.call_count >= 1
        call_kwargs = mock_langfuse.create_score.call_args.kwargs
        assert call_kwargs["observation_id"] == "obs_xyz"
        assert call_kwargs["trace_id"] == "trace_abc"

    def test_observation_path_skips_no_output(self, runner, observation_evaluator_yaml):
        """Observations with output=None must be skipped."""
        obs = make_mock_observation(obs_id="obs_noout", output=None)
        mock_langfuse = MagicMock()
        mock_langfuse.api.observations.get_many.return_value = (
            make_observation_response([obs])
        )

        mock_evaluator_config = MagicMock()
        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
        ):
            result = runner.run(since=since)

        assert result["evaluated"] == 0
        assert (
            result["sampled"] == 0
        )  # R2-F7: sampled not incremented for no-output obs
        mock_evaluator_config.evaluate.assert_not_called()

    def test_observation_path_dry_run_no_score(
        self, runner, observation_evaluator_yaml
    ):
        """dry_run=True on observation path must not call create_score()."""
        obs = make_mock_observation()
        mock_langfuse = MagicMock()
        mock_langfuse.api.observations.get_many.return_value = (
            make_observation_response([obs])
        )

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.return_value = {"score": 0.7, "reasoning": ""}

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
        ):
            result = runner.run(since=since, dry_run=True)

        assert result["evaluated"] >= 1
        assert result["scored"] == 0
        mock_langfuse.create_score.assert_not_called()

    def test_observation_path_appends_audit_log_with_observation_id(
        self, runner, observation_evaluator_yaml
    ):
        """Observation audit log entries must include observation_id."""
        obs = make_mock_observation(obs_id="obs_audit", trace_id="trace_audit")
        mock_langfuse = MagicMock()
        mock_langfuse.api.observations.get_many.return_value = (
            make_observation_response([obs])
        )

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.return_value = {"score": 0.6, "reasoning": "ok"}

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
        ):
            runner.run(since=since)

        lines = runner.audit_log_path.read_text().strip().splitlines()
        # At least one audit entry
        assert len(lines) >= 1
        entry = json.loads(lines[0])
        assert entry.get("observation_id") == "obs_audit"
        assert entry.get("trace_id") == "trace_audit"


# ---------------------------------------------------------------------------
# Tests: Cursor-based pagination for observations (BUG-217)
# ---------------------------------------------------------------------------


class TestPagePaginationObservations:
    def test_page_pagination_fetches_all_pages(
        self, runner, observation_evaluator_yaml
    ):
        """observations.get_many() must paginate via page= with total_pages."""
        obs1 = make_mock_observation(obs_id="obs_p1", trace_id="t1")
        obs2 = make_mock_observation(obs_id="obs_p2", trace_id="t2")

        mock_langfuse = MagicMock()
        # First call returns obs1 with total_pages=2; second returns obs2 with total_pages=2
        mock_langfuse.api.observations.get_many.side_effect = [
            make_observation_response([obs1], total_pages=2),
            make_observation_response([obs2], total_pages=2),
            # Additional responses for the second event_type
            make_observation_response([obs1], total_pages=2),
            make_observation_response([obs2], total_pages=2),
        ]

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.return_value = {"score": 0.8, "reasoning": ""}

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
        ):
            _result = runner.run(since=since)

        # Each event_type does 2 pages → 4 total calls for 2 event_types
        assert mock_langfuse.api.observations.get_many.call_count == 4
        # Second call for first event_type must pass page=2
        second_call_kwargs = mock_langfuse.api.observations.get_many.call_args_list[
            1
        ].kwargs
        assert second_call_kwargs.get("page") == 2

    def test_page_pagination_stops_on_single_page(
        self, runner, observation_evaluator_yaml
    ):
        """Must stop fetching when total_pages == 1."""
        obs = make_mock_observation(obs_id="obs_single")

        mock_langfuse = MagicMock()
        # Single page per event_type
        mock_langfuse.api.observations.get_many.return_value = (
            make_observation_response([obs], total_pages=1)
        )

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.return_value = {"score": 0.7, "reasoning": ""}

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
        ):
            runner.run(since=since)

        # 2 event_types, 1 page each → 2 calls total
        event_types = observation_evaluator_yaml["filter"]["event_types"]
        assert mock_langfuse.api.observations.get_many.call_count == len(event_types)

    def test_observation_get_many_passes_name_filter(
        self, runner, observation_evaluator_yaml
    ):
        """Each event_type must be passed as name= to observations.get_many()."""
        mock_langfuse = MagicMock()
        mock_langfuse.api.observations.get_many.return_value = (
            make_observation_response([])
        )

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with patch("memory.evaluator.runner.get_client", return_value=mock_langfuse):
            runner.run(since=since)

        called_names = [
            call.kwargs.get("name")
            for call in mock_langfuse.api.observations.get_many.call_args_list
        ]
        event_types = observation_evaluator_yaml["filter"]["event_types"]
        for et in event_types:
            assert et in called_names, f"event_type {et!r} not passed as name= filter"

    def test_observation_get_many_passes_time_range(
        self, runner, observation_evaluator_yaml
    ):
        """Must pass from_start_time/to_start_time to observations.get_many()."""
        mock_langfuse = MagicMock()
        mock_langfuse.api.observations.get_many.return_value = (
            make_observation_response([])
        )

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)
        until = datetime(2026, 3, 13, tzinfo=timezone.utc)

        with patch("memory.evaluator.runner.get_client", return_value=mock_langfuse):
            runner.run(since=since, until=until)

        first_call = mock_langfuse.api.observations.get_many.call_args_list[0].kwargs
        assert first_call.get("from_start_time") == since
        assert first_call.get("to_start_time") == until


# ---------------------------------------------------------------------------
# Tests: evaluation_target routing (target: field)
# ---------------------------------------------------------------------------


class TestEvaluationTargetRouting:
    def test_trace_target_routes_to_trace_list(self, runner, trace_evaluator_yaml):
        """Evaluator with target: trace must use trace.list()."""
        mock_langfuse = MagicMock()
        mock_langfuse.api.trace.list.return_value = make_paginated_response([])

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with patch("memory.evaluator.runner.get_client", return_value=mock_langfuse):
            runner.run(since=since)

        # R2-F8: use call_count instead of assert_called() for stronger assertion
        assert mock_langfuse.api.trace.list.call_count == 1
        mock_langfuse.api.observations.get_many.assert_not_called()

    def test_observation_target_routes_to_observations_get_many(
        self, runner, observation_evaluator_yaml
    ):
        """Evaluator with target: observation must use observations.get_many()."""
        mock_langfuse = MagicMock()
        mock_langfuse.api.observations.get_many.return_value = (
            make_observation_response([])
        )

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with patch("memory.evaluator.runner.get_client", return_value=mock_langfuse):
            runner.run(since=since)

        # R2-F8: 2 event_types in fixture → 2 calls to get_many
        event_types = observation_evaluator_yaml["filter"]["event_types"]
        assert mock_langfuse.api.observations.get_many.call_count == len(event_types)
        mock_langfuse.api.trace.list.assert_not_called()

    def test_missing_target_defaults_to_trace(self, runner, tmp_path):
        """Evaluator with no target: field defaults to trace path."""
        ev_dir = runner.evaluators_dir
        ev_dir.mkdir(parents=True, exist_ok=True)

        import yaml

        # No target: field
        ev = {
            "id": "EV-XX",
            "name": "test_eval",
            "score_type": "NUMERIC",
            "filter": {},
            "sampling_rate": 1.0,
            "prompt_file": "prompt.md",
        }
        (ev_dir / "evxx.yaml").write_text(yaml.dump(ev))
        (ev_dir / "prompt.md").write_text("Evaluate.")

        mock_langfuse = MagicMock()
        mock_langfuse.api.trace.list.return_value = make_paginated_response([])

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with patch("memory.evaluator.runner.get_client", return_value=mock_langfuse):
            runner.run(since=since)

        assert mock_langfuse.api.trace.list.call_count == 1
        mock_langfuse.api.observations.get_many.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: CATEGORICAL score type (EV-04)
# ---------------------------------------------------------------------------


class TestCategoricalScoreType:
    def test_categorical_score_passes_string_value(
        self, runner, categorical_evaluator_yaml
    ):
        """CATEGORICAL evaluators must pass string value to create_score()."""
        obs = make_mock_observation(obs_id="obs_cat", trace_id="trace_cat")
        mock_langfuse = MagicMock()
        mock_langfuse.api.observations.get_many.return_value = (
            make_observation_response([obs])
        )

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.return_value = {
            "score": "correct",
            "reasoning": "Correct classification",
        }

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
        ):
            runner.run(since=since)

        mock_langfuse.create_score.assert_called_once()
        call_kwargs = mock_langfuse.create_score.call_args.kwargs
        assert call_kwargs["value"] == "correct"
        assert isinstance(call_kwargs["value"], str)
        assert call_kwargs["data_type"] == "CATEGORICAL"
        assert call_kwargs["observation_id"] == "obs_cat"

    def test_categorical_score_partially_correct(
        self, runner, categorical_evaluator_yaml
    ):
        """CATEGORICAL 'partially_correct' must be passed as string."""
        obs = make_mock_observation(obs_id="obs_partial")
        mock_langfuse = MagicMock()
        mock_langfuse.api.observations.get_many.return_value = (
            make_observation_response([obs])
        )

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.return_value = {
            "score": "partially_correct",
            "reasoning": "Partial match",
        }

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
        ):
            runner.run(since=since)

        call_kwargs = mock_langfuse.create_score.call_args.kwargs
        assert call_kwargs["value"] == "partially_correct"

    def test_numeric_score_passes_float_value(self, runner, observation_evaluator_yaml):
        """NUMERIC evaluators must pass float value (not string)."""
        obs = make_mock_observation()
        mock_langfuse = MagicMock()
        mock_langfuse.api.observations.get_many.return_value = (
            make_observation_response([obs])
        )

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.return_value = {
            "score": 0.85,
            "reasoning": "Relevant",
        }

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
        ):
            runner.run(since=since)

        call_kwargs = mock_langfuse.create_score.call_args.kwargs
        assert call_kwargs["value"] == 0.85
        assert isinstance(call_kwargs["value"], float)


# ---------------------------------------------------------------------------
# Tests: error isolation
# ---------------------------------------------------------------------------


class TestRunnerErrorIsolation:
    def test_single_trace_error_does_not_kill_run(self, runner, evaluator_yaml):
        """An exception on one trace must not prevent subsequent traces from being evaluated."""
        trace1 = make_mock_trace(trace_id="trace_err", tags=["retrieval"])
        trace2 = make_mock_trace(trace_id="trace_ok", tags=["retrieval"])

        mock_langfuse = MagicMock()
        mock_langfuse.api.trace.list.return_value = make_paginated_response(
            [trace1, trace2]
        )

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.side_effect = [
            Exception("judge exploded"),
            {"score": 0.85, "reasoning": "Good result"},
        ]

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
            patch("memory.evaluator.runner.logger") as mock_logger,
        ):
            result = runner.run(since=since)

        assert result["evaluated"] == 1
        assert result["scored"] == 1
        mock_logger.error.assert_called_once()

    def test_single_observation_error_does_not_kill_run(
        self, runner, observation_evaluator_yaml
    ):
        """An exception on one observation must not prevent subsequent evaluations."""
        obs1 = make_mock_observation(obs_id="obs_err")
        obs2 = make_mock_observation(obs_id="obs_ok")

        mock_langfuse = MagicMock()
        # Both obs in same response for first event_type, empty for second
        mock_langfuse.api.observations.get_many.side_effect = [
            make_observation_response([obs1, obs2]),
            make_observation_response([]),
        ]

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.side_effect = [
            Exception("judge crashed"),
            {"score": 0.7, "reasoning": "OK"},
        ]

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
            patch("memory.evaluator.runner.logger") as mock_logger,
        ):
            result = runner.run(since=since)

        assert result["evaluated"] == 1
        mock_logger.error.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: _load_prompt
# ---------------------------------------------------------------------------


class TestLoadPrompt:
    def test_load_prompt_uses_actual_file_not_fallback(self, runner):
        """_load_prompt() should return the file contents, not the fallback stub."""
        ev_dir = runner.evaluators_dir
        ev_dir.mkdir(parents=True, exist_ok=True)

        prompt_content = "This is the actual judge prompt for testing."
        prompt_file = ev_dir / "test_prompt.md"
        prompt_file.write_text(prompt_content)

        evaluator = {"prompt_file": "test_prompt.md"}
        result = runner._load_prompt(evaluator)

        assert result == prompt_content


# ---------------------------------------------------------------------------
# Tests: _build_observation_prompt
# ---------------------------------------------------------------------------


class TestBuildObservationPrompt:
    def test_build_observation_prompt_includes_event_type(self, runner):
        """_build_observation_prompt must include the observation name (event_type)."""
        ev_dir = runner.evaluators_dir
        ev_dir.mkdir(parents=True, exist_ok=True)
        (ev_dir / "prompt.md").write_text("Evaluate the following.")

        evaluator = {"prompt_file": "prompt.md"}
        obs = make_mock_observation(name="search_query")

        result = runner._build_observation_prompt(evaluator, obs)

        assert "search_query" in result
        assert "Observation to Evaluate" in result

    def test_build_observation_prompt_different_from_trace_prompt(self, runner):
        """_build_observation_prompt must not produce 'Trace to Evaluate' header."""
        ev_dir = runner.evaluators_dir
        ev_dir.mkdir(parents=True, exist_ok=True)
        (ev_dir / "prompt.md").write_text("Evaluate.")

        evaluator = {"prompt_file": "prompt.md"}
        obs = make_mock_observation()

        result = runner._build_observation_prompt(evaluator, obs)
        assert "Trace to Evaluate" not in result
        assert "Observation to Evaluate" in result


# ---------------------------------------------------------------------------
# Tests: R2-F2 — dry_run does not write audit log
# ---------------------------------------------------------------------------


class TestDryRunAuditLog:
    def test_dry_run_does_not_write_audit_log_trace(self, runner, evaluator_yaml):
        """dry_run=True must NOT write audit log for trace path."""
        trace = make_mock_trace(trace_id="trace_dry", tags=["retrieval"])
        mock_langfuse = MagicMock()
        mock_langfuse.api.trace.list.return_value = make_paginated_response([trace])

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.return_value = {"score": 0.7, "reasoning": "ok"}

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
        ):
            runner.run(since=since, dry_run=True)

        assert not runner.audit_log_path.exists()

    def test_dry_run_does_not_write_audit_log_observation(
        self, runner, observation_evaluator_yaml
    ):
        """dry_run=True must NOT write audit log for observation path."""
        obs = make_mock_observation(obs_id="obs_dry", trace_id="trace_dry")
        mock_langfuse = MagicMock()
        mock_langfuse.api.observations.get_many.return_value = (
            make_observation_response([obs])
        )

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.return_value = {"score": 0.6, "reasoning": "ok"}

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
        ):
            runner.run(since=since, dry_run=True)

        assert not runner.audit_log_path.exists()


# ---------------------------------------------------------------------------
# Tests: R2-F5 — observation with no trace_id is skipped
# ---------------------------------------------------------------------------


class TestObservationNoTraceId:
    def test_observation_with_no_trace_id_is_skipped(
        self, runner, observation_evaluator_yaml
    ):
        """Observation with empty trace_id must be skipped with a warning."""
        obs = make_mock_observation(obs_id="obs_notrace", trace_id="")
        obs.trace_id = ""

        mock_langfuse = MagicMock()
        mock_langfuse.api.observations.get_many.return_value = (
            make_observation_response([obs])
        )

        mock_evaluator_config = MagicMock()
        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
            patch("memory.evaluator.runner.logger") as mock_logger,
        ):
            result = runner.run(since=since)

        assert result["evaluated"] == 0
        assert result["scored"] == 0
        mock_evaluator_config.evaluate.assert_not_called()
        mock_logger.warning.assert_called()


# ---------------------------------------------------------------------------
# Tests: R1-F3 — invalid categorical value is skipped
# ---------------------------------------------------------------------------


class TestCategoricalValidation:
    def test_invalid_categorical_value_skipped(
        self, runner, categorical_evaluator_yaml
    ):
        """Categorical score not in categories list must be skipped with warning."""
        obs = make_mock_observation(obs_id="obs_badcat", trace_id="trace_badcat")
        mock_langfuse = MagicMock()
        mock_langfuse.api.observations.get_many.return_value = (
            make_observation_response([obs])
        )

        mock_evaluator_config = MagicMock()
        # "unknown_label" is not in categories: ["correct", "partially_correct", "incorrect"]
        mock_evaluator_config.evaluate.return_value = {
            "score": "unknown_label",
            "reasoning": "hallucinated category",
        }

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
            patch("memory.evaluator.runner.logger") as mock_logger,
        ):
            result = runner.run(since=since)

        # evaluated is incremented before validation, scored is not
        assert result["scored"] == 0
        mock_langfuse.create_score.assert_not_called()
        mock_logger.warning.assert_called()

    def test_valid_categorical_value_is_scored(
        self, runner, categorical_evaluator_yaml
    ):
        """Categorical score within categories list must be scored normally."""
        obs = make_mock_observation(obs_id="obs_goodcat", trace_id="trace_goodcat")
        mock_langfuse = MagicMock()
        mock_langfuse.api.observations.get_many.return_value = (
            make_observation_response([obs])
        )

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.return_value = {
            "score": "correct",
            "reasoning": "valid",
        }

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
        ):
            result = runner.run(since=since)

        assert result["scored"] == 1
        mock_langfuse.create_score.assert_called()


# ---------------------------------------------------------------------------
# TD-284: Evaluation metrics — score accumulation, threshold breach, metrics push
# ---------------------------------------------------------------------------


class TestEvalScoreAccumulation:
    """_ev_scores tracks per-evaluator scores and resets between run() calls."""

    def test_ev_scores_reset_between_runs(self, runner, trace_evaluator_yaml):
        """C-1: _ev_scores must be empty at the start of each run() call."""
        mock_langfuse = MagicMock()
        mock_langfuse.api.trace.list.return_value = MagicMock(
            data=[], meta=MagicMock(next_page=None)
        )
        since = datetime(2026, 3, 1, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch("memory.evaluator.runner.push_evaluation_metrics_async", None),
        ):
            # First run — no scores (empty result set)
            runner.run(since=since)
            # Manually inject stale scores to simulate corrupted state
            runner._ev_scores["bootstrap_quality"] = [0.1, 0.2, 0.3]

            # Second run must reset _ev_scores before processing
            runner.run(since=since)

        assert runner._ev_scores == {}, "_ev_scores not reset between run() calls"

    def test_compute_avg_score_returns_none_when_empty(self, runner):
        """_compute_avg_score returns None when no scores accumulated."""
        result = runner._compute_avg_score("nonexistent_evaluator")
        assert result is None

    def test_compute_avg_score_returns_correct_average(self, runner):
        """_compute_avg_score returns mean of accumulated scores."""
        runner._ev_scores["test_ev"] = [0.8, 0.6, 1.0]
        result = runner._compute_avg_score("test_ev")
        assert result == pytest.approx(0.8)

    def test_compute_avg_score_single_value(self, runner):
        """_compute_avg_score with a single score returns that score."""
        runner._ev_scores["test_ev"] = [0.75]
        assert runner._compute_avg_score("test_ev") == pytest.approx(0.75)


class TestEvalThresholdBreach:
    """TD-284: threshold breach detection and metrics push in run()."""

    def _run_with_score(
        self, runner, score, threshold=None, ev_name="retrieval_relevance"
    ):
        """Run runner with a mock evaluator that returns the given score."""
        mock_langfuse = MagicMock()
        trace = MagicMock()
        trace.id = "trace-001"
        trace.name = "session_bootstrap"  # matches trace_evaluator_yaml filter
        trace.input = "test input"
        trace.output = "test output"
        trace.metadata = {}
        trace.tags = []

        mock_langfuse.api.trace.list.return_value = make_paginated_response([trace])

        mock_evaluator_config = MagicMock()
        mock_evaluator_config.evaluate.return_value = {
            "score": score,
            "reasoning": "test",
        }

        config_override = {}
        if threshold is not None:
            config_override = {"thresholds": {ev_name: threshold}}

        since = datetime(2026, 3, 1, tzinfo=timezone.utc)

        with (
            patch("memory.evaluator.runner.get_client", return_value=mock_langfuse),
            patch.object(runner, "evaluator_config", mock_evaluator_config),
            patch.object(runner, "config", {**runner.config, **config_override}),
        ):
            return runner.run(since=since)

    def test_threshold_breach_detected_when_score_below_threshold(
        self, runner, trace_evaluator_yaml
    ):
        """TD-284: breach=1 when avg_score < threshold."""
        breach_calls = []

        def capture_push(**kwargs):
            breach_calls.append(kwargs)

        with patch(
            "memory.evaluator.runner.push_evaluation_metrics_async", capture_push
        ):
            self._run_with_score(
                runner, score=0.4, threshold=0.7, ev_name="bootstrap_quality"
            )

        assert len(breach_calls) == 1
        assert breach_calls[0]["threshold_breach"] == 1
        assert breach_calls[0]["avg_score"] == pytest.approx(0.4)

    def test_no_breach_when_score_meets_threshold(self, runner, trace_evaluator_yaml):
        """TD-284: breach=0 when avg_score >= threshold."""
        breach_calls = []

        def capture_push(**kwargs):
            breach_calls.append(kwargs)

        with patch(
            "memory.evaluator.runner.push_evaluation_metrics_async", capture_push
        ):
            self._run_with_score(
                runner, score=0.8, threshold=0.7, ev_name="bootstrap_quality"
            )

        assert len(breach_calls) == 1
        assert breach_calls[0]["threshold_breach"] == 0

    def test_no_breach_when_no_threshold_configured(self, runner, trace_evaluator_yaml):
        """TD-284: breach=0 when no threshold configured for evaluator."""
        breach_calls = []

        def capture_push(**kwargs):
            breach_calls.append(kwargs)

        with patch(
            "memory.evaluator.runner.push_evaluation_metrics_async", capture_push
        ):
            self._run_with_score(
                runner, score=0.1, threshold=None, ev_name="bootstrap_quality"
            )

        assert len(breach_calls) == 1
        assert breach_calls[0]["threshold_breach"] == 0

    def test_push_skipped_when_push_fn_is_none(self, runner, trace_evaluator_yaml):
        """TD-284: no error when push_evaluation_metrics_async is None (not installed)."""
        with (patch("memory.evaluator.runner.push_evaluation_metrics_async", None),):
            # Must not raise
            self._run_with_score(
                runner, score=0.5, threshold=0.7, ev_name="bootstrap_quality"
            )

    def test_push_called_with_evaluator_name(self, runner, trace_evaluator_yaml):
        """TD-284: push call includes correct evaluator_name."""
        push_calls = []

        with patch(
            "memory.evaluator.runner.push_evaluation_metrics_async",
            lambda **kw: push_calls.append(kw),
        ):
            self._run_with_score(runner, score=0.9, ev_name="bootstrap_quality")

        assert len(push_calls) == 1
        assert push_calls[0]["evaluator_name"] == "bootstrap_quality"
        assert "duration_seconds" in push_calls[0]
        assert "runs_count" in push_calls[0]

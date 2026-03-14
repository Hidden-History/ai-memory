# LANGFUSE: V3 SDK ONLY. See LANGFUSE-INTEGRATION-SPEC.md
"""Tests for memory.evaluator.runner — EvaluatorRunner core pipeline.

Tests trace filtering, sampling, score attachment, and pagination using
mocked Langfuse client.

PLAN-012 Phase 2 — AC-8
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
  model_name: llama3.2:8b
  temperature: 0.0
  max_tokens: 512
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
def evaluator_yaml(tmp_path, minimal_config) -> dict:
    """Create a single evaluator YAML in the evaluators directory."""
    runner = EvaluatorRunner(config_path=str(minimal_config))
    ev_yaml = {
        "id": "EV-01",
        "name": "retrieval_relevance",
        "score_type": "NUMERIC",
        "target": "observation",
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


def make_paginated_response(traces: list, total_pages=1):
    response = MagicMock()
    response.data = traces
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

    def test_matches_expected_md5(self, runner):
        since = datetime(2026, 3, 13, 0, 0, 0, tzinfo=timezone.utc)
        expected = hashlib.md5(
            f"trace123:retrieval_relevance:{since.isoformat()}".encode()
        ).hexdigest()
        assert (
            runner._make_score_id("trace123", "retrieval_relevance", since) == expected
        )


# ---------------------------------------------------------------------------
# Tests: run() — mocked Langfuse client
# ---------------------------------------------------------------------------


class TestRunnerRun:
    def test_run_with_no_evaluators_returns_zero_summary(self, runner):
        """When evaluators_dir is empty, run() returns all-zero summary."""
        mock_langfuse = MagicMock()
        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with patch("memory.evaluator.runner.get_client", return_value=mock_langfuse):
            # evaluators_dir is empty (created by fixture but no YAMLs)
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
        mock_evaluator_config.evaluate.assert_not_called()

    def test_run_uses_page_pagination(self, runner, evaluator_yaml):
        """Should advance page number when more pages are available."""
        trace1 = make_mock_trace(trace_id="trace_p1", tags=["retrieval"])
        trace2 = make_mock_trace(trace_id="trace_p2", tags=["retrieval"])

        mock_langfuse = MagicMock()
        # First call returns trace1 with total_pages=2
        # Second call returns trace2 with total_pages=2 (page 2 of 2, stops)
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
        """--evaluator EV-01 should only load EV-01 definition."""
        ev_dir = runner.evaluators_dir
        ev_dir.mkdir(parents=True, exist_ok=True)

        import yaml

        # Create two evaluators
        ev01 = {
            "id": "EV-01",
            "name": "retrieval_relevance",
            "score_type": "NUMERIC",
            "filter": {},
            "sampling_rate": 1.0,
            "prompt_file": "prompt.md",
        }
        ev02 = {
            "id": "EV-02",
            "name": "injection_value",
            "score_type": "BOOLEAN",
            "filter": {},
            "sampling_rate": 1.0,
            "prompt_file": "prompt.md",
        }
        (ev_dir / "ev01.yaml").write_text(yaml.dump(ev01))
        (ev_dir / "ev02.yaml").write_text(yaml.dump(ev02))
        (ev_dir / "prompt.md").write_text("Evaluate this.")

        mock_langfuse = MagicMock()
        mock_langfuse.api.trace.list.return_value = make_paginated_response([])

        since = datetime(2026, 3, 12, tzinfo=timezone.utc)

        with patch("memory.evaluator.runner.get_client", return_value=mock_langfuse):
            runner.run(evaluator_id="EV-01", since=since)

        # api.trace.list should have been called once (for EV-01 only)
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
        # Must import/use get_client
        assert "get_client" in source
        # Must NOT instantiate Langfuse() directly (excluding comments and strings)
        non_comment_lines = [
            line for line in source.splitlines() if not line.strip().startswith("#")
        ]
        non_comment_source = "\n".join(non_comment_lines)
        assert "Langfuse()" not in non_comment_source


# ---------------------------------------------------------------------------
# Tests: _load_prompt
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

        # Second trace must still be evaluated
        assert result["evaluated"] == 1
        assert result["scored"] == 1
        # Error must be logged for the first trace
        mock_logger.error.assert_called_once()


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

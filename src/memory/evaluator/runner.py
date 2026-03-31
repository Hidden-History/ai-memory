# LANGFUSE: V4 SDK ONLY. See LANGFUSE-INTEGRATION-SPEC.md
# FORBIDDEN: Langfuse() constructor, start_span(), start_generation(), langfuse_context
# REQUIRED: get_client(), create_score(), flush()
"""Evaluation runner — fetches traces and observations, evaluates, attaches scores.

Core pipeline:
  1. Load evaluator config + evaluator definitions
  2. Per evaluator, read target: "trace" or "observation" (per-evaluator YAML field)
  3. Trace path (EV-05, EV-06): page-based pagination via trace.list()
     - uses from_timestamp/to_timestamp/page/meta.total_pages (V3 trace API)
  4. Observation path (EV-01-EV-04): page-based pagination via observations.get_many()
     - uses from_start_time/to_start_time/page/meta.total_pages (V3 observation API)
  5. Filter observations by name (event_type) — server-side via name= parameter (Path B)
  6. Sample traces/observations per evaluator's sampling_rate
  7. Evaluate each trace/observation via configurable LLM judge
  8. Attach scores to Langfuse via create_score() (idempotent via score_id=)
  9. Log each evaluation to audit log

Note: evaluation_targets in evaluator_config.yaml is DEPRECATED.
      Use the per-evaluator target: field in each evaluator YAML instead.

PLAN-012 Phase 2 — Section 5.4
S-16.3: Observation-level evaluation + page-based observation pagination
"""

import hashlib
import json
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import TRACE_CONTENT_MAX
from .provider import EvaluatorConfig

try:
    from ..metrics_push import push_evaluation_metrics_async
except ImportError:  # pragma: no cover
    push_evaluation_metrics_async = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Module-level import for patchability in tests.
# Uses try/except so runner can be imported without langfuse installed.
try:
    from langfuse import get_client
except ImportError:  # pragma: no cover

    def get_client():  # type: ignore[misc]
        raise ImportError(
            "langfuse package not installed — pip install 'langfuse>=4.0.0,<4.1.0'"
        )


class EvaluatorRunner:
    """Core evaluation pipeline for LLM-as-Judge scoring of Langfuse traces and observations."""

    def __init__(self, config_path: str):
        """Load evaluator config and prepare runner.

        Args:
            config_path: Path to evaluator_config.yaml
        """
        import yaml

        self.config_path = config_path
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.evaluator_config = EvaluatorConfig.from_yaml(config_path)
        self.evaluators_dir = Path(self.config.get("evaluators_dir", "./evaluators/"))
        self.audit_log_path = Path(
            self.config.get("audit", {}).get(
                "log_file", ".audit/logs/evaluations.jsonl"
            )
        )
        self._ev_scores: dict[str, list[float]] = {}

    def _load_evaluators(self, evaluator_id: str | None = None) -> list[dict]:
        """Load evaluator definitions from YAML files.

        Args:
            evaluator_id: Optional evaluator ID to filter (e.g., "EV-01")

        Returns:
            List of evaluator definition dicts
        """
        import yaml

        evaluators = []
        if not self.evaluators_dir.exists():
            logger.warning("Evaluators directory not found: %s", self.evaluators_dir)
            return evaluators

        for yaml_file in sorted(self.evaluators_dir.glob("*.yaml")):
            with open(yaml_file) as f:
                ev = yaml.safe_load(f)
            if evaluator_id and ev.get("id") != evaluator_id:
                continue
            evaluators.append(ev)

        return evaluators

    def _load_prompt(self, evaluator: dict) -> str:
        """Load the prompt template for an evaluator.

        Args:
            evaluator: Evaluator definition dict

        Returns:
            Prompt template string
        """
        prompt_file = evaluator.get("prompt_file", "")
        prompt_path = self.evaluators_dir / prompt_file
        if prompt_path.exists():
            return prompt_path.read_text()
        logger.warning("Prompt file not found: %s", prompt_path)
        return "Evaluate the following trace data."

    def _matches_filter(self, trace: Any, ev_filter: dict) -> bool:
        """Check if a trace matches the evaluator's filter criteria.

        Args:
            trace: Langfuse trace object
            ev_filter: Filter dict with optional 'event_types' and 'tags' keys

        Returns:
            True if trace matches all filter criteria
        """
        if not ev_filter:
            return True

        # Check tags filter — trace must have at least one matching tag
        filter_tags = ev_filter.get("tags", [])
        if filter_tags:
            trace_tags = getattr(trace, "tags", None) or []
            if not any(tag in trace_tags for tag in filter_tags):
                return False

        # Check event_types filter — trace name must match an event type
        filter_event_types = ev_filter.get("event_types", [])
        if filter_event_types:
            trace_name = getattr(trace, "name", "") or ""
            if trace_name not in filter_event_types:
                return False

        return True

    def _build_prompt(self, evaluator: dict, trace: Any) -> str:
        """Build evaluation prompt from template + trace data.

        Args:
            evaluator: Evaluator definition dict
            trace: Langfuse trace object

        Returns:
            Formatted evaluation prompt
        """
        template = self._load_prompt(evaluator)

        trace_input = str(getattr(trace, "input", "") or "")[:TRACE_CONTENT_MAX]
        trace_output = str(getattr(trace, "output", "") or "")[:TRACE_CONTENT_MAX]
        trace_metadata = str(getattr(trace, "metadata", {}) or {})[:TRACE_CONTENT_MAX]

        return (
            f"{template}\n\n"
            f"## Trace to Evaluate\n\n"
            f"**Input**: {trace_input}\n\n"
            f"**Output**: {trace_output}\n\n"
            f"**Metadata**: {trace_metadata}"
        )

    def _build_observation_prompt(self, evaluator: dict, observation: Any) -> str:
        """Build evaluation prompt from template + observation data.

        Do NOT pass observation objects to _build_prompt() — observation schema
        differs from trace schema (e.g. no tags, name is event_type).

        Args:
            evaluator: Evaluator definition dict
            observation: Langfuse ObservationV2 object

        Returns:
            Formatted evaluation prompt
        """
        template = self._load_prompt(evaluator)

        obs_name = str(getattr(observation, "name", "") or "")
        obs_input = str(getattr(observation, "input", "") or "")[:TRACE_CONTENT_MAX]
        obs_output = str(getattr(observation, "output", "") or "")[:TRACE_CONTENT_MAX]
        obs_metadata = str(getattr(observation, "metadata", {}) or {})[
            :TRACE_CONTENT_MAX
        ]

        return (
            f"{template}\n\n"
            f"## Observation to Evaluate\n\n"
            f"**Event Type**: {obs_name}\n\n"
            f"**Input**: {obs_input}\n\n"
            f"**Output**: {obs_output}\n\n"
            f"**Metadata**: {obs_metadata}"
        )

    def _make_score_id(
        self,
        trace_id: str,
        evaluator_name: str,
        since: datetime,
        observation_id: str | None = None,
    ) -> str:
        """Generate deterministic score ID for idempotency.

        Includes observation_id in the hash when present — without it, multiple
        observations in the same trace would produce IDENTICAL score_ids (BUG-S163).

        Seed format:
          - With observation: f"{trace_id}:{observation_id}:{evaluator_name}:{since.isoformat()}"
          - Without observation: f"{trace_id}:{evaluator_name}:{since.isoformat()}"

        Args:
            trace_id: Langfuse trace ID
            evaluator_name: Evaluator name (e.g., "retrieval_relevance")
            since: Start of evaluation window
            observation_id: Optional Langfuse observation ID (for observation-level scores)

        Returns:
            32-character hex MD5 string
        """
        if observation_id:
            seed = f"{trace_id}:{observation_id}:{evaluator_name}:{since.isoformat()}"
        else:
            seed = f"{trace_id}:{evaluator_name}:{since.isoformat()}"
        return hashlib.md5(seed.encode()).hexdigest()

    def _append_audit_log(self, entry: dict) -> None:
        """Append an evaluation result to the JSONL audit log."""
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.audit_log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _compute_avg_score(self, ev_name: str) -> float | None:
        """Return average of accumulated scores for ev_name, or None if no scores."""
        scores = self._ev_scores.get(ev_name, [])
        if not scores:
            return None
        return sum(scores) / len(scores)

    def _run_observation_evaluator(
        self,
        langfuse: Any,
        evaluator: dict,
        ev_name: str,
        since: datetime,
        until: datetime,
        dry_run: bool,
        batch_size: int,
    ) -> tuple[int, int, int, int]:
        """Run observation-level evaluation for a single evaluator.

        Fetches observations via observations.get_many() with page-based pagination
        (BUG-217). Filters by observation name (event_type) server-side via name=
        parameter (Path B — tags are trace-level only in V3).

        Args:
            langfuse: Langfuse client from get_client()
            evaluator: Evaluator definition dict
            ev_name: Evaluator name string
            since: Start of evaluation window
            until: End of evaluation window
            dry_run: If True, evaluate but do not save scores
            batch_size: Number of observations per cursor page

        Returns:
            Tuple of (fetched, sampled, evaluated, scored)
        """
        ev_filter = evaluator.get("filter", {})
        sampling_rate = float(evaluator.get("sampling_rate", 1.0))
        score_type = evaluator.get("score_type", "NUMERIC")
        event_types = ev_filter.get("event_types", [])

        # If no event_types defined, fetch all observations (no name filter).
        # Otherwise iterate once per event_type using server-side name= filter.
        name_filters: list[str | None] = event_types if event_types else [None]

        fetched = sampled = evaluated = scored = 0

        try:  # R2-F3: catch fetch-level errors so one evaluator doesn't kill the whole run
            for name_filter in name_filters:
                page = 1

                while True:
                    obs_response = langfuse.api.legacy.observations_v1.get_many(
                        name=name_filter,
                        from_start_time=since,
                        to_start_time=until,
                        page=page,
                        limit=batch_size,
                    )
                    observations = obs_response.data
                    _total_pages = obs_response.meta.total_pages
                    fetched += len(observations)

                    for obs in observations:
                        # Apply sampling
                        if random.random() > sampling_rate:
                            continue

                        obs_id = obs.id
                        trace_id = getattr(obs, "trace_id", None) or ""

                        # R2-F5: skip observations with no trace_id
                        if not trace_id:
                            logger.warning(
                                "Observation %s has no trace_id — skipping", obs_id
                            )
                            continue

                        # R2-F7: check output BEFORE incrementing sampled
                        if getattr(obs, "output", None) is None:
                            continue

                        # Note: 'sampled' counts observations that passed random gate + trace_id + output guards — not raw sampling rate
                        sampled += 1

                        try:
                            prompt = self._build_observation_prompt(evaluator, obs)
                            result = self.evaluator_config.evaluate(prompt)
                            if result.get("score") is None:
                                logger.warning(
                                    "Evaluator returned null score for observation %s",
                                    obs_id,
                                )
                                continue

                            evaluated += 1

                            # Track score for metrics (TD-284)
                            if isinstance(result["score"], (int, float)):
                                self._ev_scores.setdefault(ev_name, []).append(
                                    float(result["score"])
                                )

                            # Attach score (idempotent via score_id)
                            if not dry_run:
                                score_id = self._make_score_id(
                                    trace_id, ev_name, since, observation_id=obs_id
                                )
                                # CATEGORICAL scores use string value; NUMERIC/BOOLEAN use float
                                score_value = (
                                    str(result["score"])
                                    if score_type == "CATEGORICAL"
                                    else result["score"]
                                )
                                # R1-F3: validate categorical value against defined categories
                                if score_type == "CATEGORICAL":
                                    valid_categories = evaluator.get("categories", [])
                                    if (
                                        valid_categories
                                        and str(result["score"]) not in valid_categories
                                    ):
                                        logger.warning(
                                            "Observation %s: categorical value %r not in "
                                            "categories %s — skipping",
                                            obs_id,
                                            result["score"],
                                            valid_categories,
                                        )
                                        continue
                                langfuse.create_score(
                                    score_id=score_id,
                                    trace_id=trace_id,
                                    observation_id=obs_id,
                                    name=ev_name,
                                    value=score_value,
                                    data_type=score_type,
                                    comment=str(result.get("reasoning", ""))[
                                        :TRACE_CONTENT_MAX
                                    ],
                                )
                                scored += 1

                                # R2-F2: audit log only written when not dry_run
                                self._append_audit_log(
                                    {
                                        "timestamp": datetime.now(
                                            tz=timezone.utc
                                        ).isoformat(),
                                        "evaluator_id": evaluator.get("id"),
                                        "evaluator_name": ev_name,
                                        "trace_id": trace_id,
                                        "observation_id": obs_id,
                                        "score": result["score"],
                                        "reasoning": str(result.get("reasoning", ""))[
                                            :500
                                        ],
                                        "dry_run": dry_run,
                                    }
                                )

                            reasoning_preview = str(result.get("reasoning", ""))[:80]
                            print(
                                f"  [{ev_name}] obs={obs_id[:8]}... trace={trace_id[:8]}... "
                                f"score={result['score']} | {reasoning_preview}"
                            )
                        except Exception as exc:
                            logger.error(
                                "Error evaluating observation %s with %s: %s",
                                obs_id,
                                ev_name,
                                exc,
                            )
                            continue

                    if page >= _total_pages or not observations:
                        break
                    page += 1

        except Exception as exc:
            logger.error("Evaluator %s: error fetching observations: %s", ev_name, exc)

        return fetched, sampled, evaluated, scored

    def _run_trace_evaluator(
        self,
        langfuse: Any,
        evaluator: dict,
        ev_name: str,
        since: datetime,
        until: datetime,
        dry_run: bool,
        batch_size: int,
    ) -> tuple[int, int, int, int]:
        """Run trace-level evaluation for a single evaluator.

        Fetches traces via trace.list() with page-based pagination.
        Uses from_timestamp/to_timestamp/page/meta.total_pages (V3 trace API).

        Args:
            langfuse: Langfuse client from get_client()
            evaluator: Evaluator definition dict
            ev_name: Evaluator name string
            since: Start of evaluation window
            until: End of evaluation window
            dry_run: If True, evaluate but do not save scores
            batch_size: Number of traces per page

        Returns:
            Tuple of (fetched, sampled, evaluated, scored)
        """
        ev_filter = evaluator.get("filter", {})
        sampling_rate = float(evaluator.get("sampling_rate", 1.0))
        score_type = evaluator.get("score_type", "NUMERIC")

        fetched = sampled = evaluated = scored = 0
        page = 1  # V3 trace.list() is page-based (1-indexed)

        try:  # R2-F3: catch fetch-level errors so one evaluator doesn't kill the whole run
            while True:
                traces_response = langfuse.api.trace.list(
                    from_timestamp=since,
                    to_timestamp=until,
                    page=page,
                    limit=batch_size,
                )
                traces = traces_response.data or []
                fetched += len(traces)

                for trace in traces:
                    # Filter first, then sample from matching traces only (UF-4)
                    if not self._matches_filter(trace, ev_filter):
                        continue

                    # Apply sampling
                    if random.random() > sampling_rate:
                        continue

                    # R2-F7: check output BEFORE incrementing sampled
                    if getattr(trace, "output", None) is None:
                        continue

                    sampled += 1

                    # Build prompt and evaluate — isolated per trace (UF-3)
                    try:
                        prompt = self._build_prompt(evaluator, trace)
                        result = self.evaluator_config.evaluate(prompt)
                        if result.get("score") is None:
                            logger.warning(
                                "Evaluator returned null score for trace %s",
                                trace.id,
                            )
                            continue

                        evaluated += 1

                        # Track score for metrics (TD-284)
                        if isinstance(result["score"], (int, float)):
                            self._ev_scores.setdefault(ev_name, []).append(
                                float(result["score"])
                            )

                        # Attach score to Langfuse (idempotent via score_id)
                        if not dry_run:
                            score_id = self._make_score_id(trace.id, ev_name, since)
                            # CATEGORICAL scores use string value; NUMERIC/BOOLEAN use float
                            score_value = (
                                str(result["score"])
                                if score_type == "CATEGORICAL"
                                else result["score"]
                            )
                            # R1-F3: validate categorical value against defined categories
                            if score_type == "CATEGORICAL":
                                valid_categories = evaluator.get("categories", [])
                                if (
                                    valid_categories
                                    and str(result["score"]) not in valid_categories
                                ):
                                    logger.warning(
                                        "Trace %s: categorical value %r not in "
                                        "categories %s — skipping",
                                        trace.id,
                                        result["score"],
                                        valid_categories,
                                    )
                                    continue
                            langfuse.create_score(
                                score_id=score_id,
                                trace_id=trace.id,
                                name=ev_name,
                                value=score_value,
                                data_type=score_type,
                                comment=str(result.get("reasoning", ""))[
                                    :TRACE_CONTENT_MAX
                                ],
                            )
                            scored += 1

                            # R2-F2: audit log only written when not dry_run
                            self._append_audit_log(
                                {
                                    "timestamp": datetime.now(
                                        tz=timezone.utc
                                    ).isoformat(),
                                    "evaluator_id": evaluator.get("id"),
                                    "evaluator_name": ev_name,
                                    "trace_id": trace.id,
                                    "score": result["score"],
                                    "reasoning": str(result.get("reasoning", ""))[:500],
                                    "dry_run": dry_run,
                                }
                            )

                        reasoning_preview = str(result.get("reasoning", ""))[:80]
                        print(
                            f"  [{ev_name}] trace={trace.id[:8]}... "
                            f"score={result['score']} | {reasoning_preview}"
                        )
                    except Exception as exc:
                        logger.error(
                            "Error evaluating trace %s with %s: %s",
                            trace.id,
                            ev_name,
                            exc,
                        )
                        continue

                # Page-based pagination — advance or stop (V3 trace.list() API)
                meta = getattr(traces_response, "meta", None)
                total_pages = getattr(meta, "total_pages", 1) if meta else 1
                if page >= total_pages or not traces:
                    break
                page += 1

        except Exception as exc:
            logger.error("Evaluator %s: error fetching traces: %s", ev_name, exc)

        return fetched, sampled, evaluated, scored

    def run(
        self,
        evaluator_id: str | None = None,
        *,
        since: datetime,
        until: datetime | None = None,
        dry_run: bool = False,
        batch_size: int = 10,
    ) -> dict:
        """Run evaluations for all (or one) evaluator.

        Routes each evaluator to the correct path based on the per-evaluator
        YAML target: field ("trace" or "observation"). The global evaluation_targets
        section in evaluator_config.yaml is DEPRECATED in favour of per-evaluator target:.

        Args:
            evaluator_id: Optional evaluator ID to run (e.g., "EV-01")
            since: Start of evaluation window (required — CLI provides this)
            until: End of evaluation window (default: now)
            dry_run: If True, evaluate but do not save scores to Langfuse
            batch_size: Number of traces/observations to fetch per page/cursor

        Returns:
            Summary dict with counts: fetched, sampled, evaluated, scored
        """
        # Reset per-run score accumulator (C-1: avoid cross-run average corruption)
        self._ev_scores = {}

        # V3 singleton — NEVER use Langfuse() constructor directly
        langfuse = get_client()

        if until is None:
            until = datetime.now(tz=timezone.utc)

        evaluators = self._load_evaluators(evaluator_id)
        if not evaluators:
            logger.warning(
                "No evaluators found (dir=%s, id=%s)", self.evaluators_dir, evaluator_id
            )
            return {"fetched": 0, "sampled": 0, "evaluated": 0, "scored": 0}

        total_fetched = 0
        total_sampled = 0
        total_evaluated = 0
        total_scored = 0

        try:
            for evaluator in evaluators:
                ev_name = evaluator.get("name", evaluator.get("id", "unknown"))
                # Per-evaluator target field is source of truth (DEPRECATED: global evaluation_targets)
                target = evaluator.get("target", "trace")

                print(
                    f"\n--- Running {evaluator.get('id', '?')}: {ev_name} (target={target}) ---"
                )

                ev_start = time.time()
                if target == "observation":
                    f, s, e, sc = self._run_observation_evaluator(
                        langfuse, evaluator, ev_name, since, until, dry_run, batch_size
                    )
                else:
                    # Default: trace-level evaluation (EV-05, EV-06)
                    f, s, e, sc = self._run_trace_evaluator(
                        langfuse, evaluator, ev_name, since, until, dry_run, batch_size
                    )
                ev_duration = time.time() - ev_start

                total_fetched += f
                total_sampled += s
                total_evaluated += e
                total_scored += sc

                # Push metrics and check threshold (TD-284)
                avg_score = self._compute_avg_score(ev_name)
                threshold = self.config.get("thresholds", {}).get(ev_name)
                breach = (
                    1
                    if avg_score is not None
                    and threshold is not None
                    and avg_score < threshold
                    else 0
                )
                if push_evaluation_metrics_async is not None:
                    push_evaluation_metrics_async(
                        evaluator_name=ev_name,
                        avg_score=avg_score if avg_score is not None else 0.0,
                        runs_count=e,
                        duration_seconds=ev_duration,
                        threshold_breach=breach,
                    )

                print(f"  Evaluated: {e} | Scored: {sc}")

        finally:
            # Flush all buffered scores to Langfuse — runs even if an error occurs (UF-5)
            langfuse.flush()

        summary = {
            "fetched": total_fetched,
            "sampled": total_sampled,
            "evaluated": total_evaluated,
            "scored": total_scored,
        }
        logger.info("Evaluation complete: %s", summary)
        return summary

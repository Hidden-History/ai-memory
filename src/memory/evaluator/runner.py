# LANGFUSE: V3 SDK ONLY. See LANGFUSE-INTEGRATION-SPEC.md
# FORBIDDEN: Langfuse() constructor, start_span(), start_generation(), langfuse_context
# REQUIRED: get_client(), create_score(), flush()
"""Evaluation runner — fetches traces, evaluates, attaches scores.

Core pipeline:
  1. Load evaluator config + evaluator definitions
  2. Fetch traces using page-based pagination (V3 SDK)
  3. Filter traces by evaluator criteria (event_types, tags)
  4. Sample traces per evaluator's sampling_rate
  5. Evaluate each trace via configurable LLM judge
  6. Attach scores to Langfuse via create_score() (idempotent)
  7. Log each evaluation to audit log

PLAN-012 Phase 2 — Section 5.4
"""

import hashlib
import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import TRACE_CONTENT_MAX
from .provider import EvaluatorConfig

logger = logging.getLogger(__name__)

# Module-level import for patchability in tests.
# Uses try/except so runner can be imported without langfuse installed.
try:
    from langfuse import get_client
except ImportError:  # pragma: no cover

    def get_client():  # type: ignore[misc]
        raise ImportError(
            "langfuse package not installed — pip install 'langfuse>=3.0,<4.0'"
        )


class EvaluatorRunner:
    """Core evaluation pipeline for LLM-as-Judge scoring of Langfuse traces."""

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

    def _make_score_id(
        self, trace_id: str, evaluator_name: str, since: datetime
    ) -> str:
        """Generate deterministic score ID for idempotency.

        Uses MD5 of f"{trace_id}:{evaluator_name}:{since.isoformat()}"
        so re-running the same evaluation window produces the same score ID.

        Args:
            trace_id: Langfuse trace ID
            evaluator_name: Evaluator name (e.g., "retrieval_relevance")
            since: Start of evaluation window

        Returns:
            32-character hex MD5 string
        """
        seed = f"{trace_id}:{evaluator_name}:{since.isoformat()}"
        return hashlib.md5(seed.encode()).hexdigest()

    def _append_audit_log(self, entry: dict) -> None:
        """Append an evaluation result to the JSONL audit log."""
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.audit_log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

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

        Args:
            evaluator_id: Optional evaluator ID to run (e.g., "EV-01")
            since: Start of evaluation window (required — CLI provides this)
            until: End of evaluation window (default: now)
            dry_run: If True, evaluate but do not save scores to Langfuse
            batch_size: Number of traces to fetch per page

        Returns:
            Summary dict with counts: fetched, sampled, evaluated, scored
        """
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
                sampling_rate = float(evaluator.get("sampling_rate", 1.0))
                ev_filter = evaluator.get("filter", {})

                print(f"\n--- Running {evaluator.get('id', '?')}: {ev_name} ---")

                page = 1  # V3 uses page-based pagination (1-indexed)

                while True:
                    traces_response = langfuse.api.trace.list(
                        from_timestamp=since,
                        to_timestamp=until,
                        page=page,
                        limit=batch_size,
                    )
                    traces = traces_response.data or []
                    total_fetched += len(traces)

                    for trace in traces:
                        # Filter first, then sample from matching traces only (UF-4)
                        if not self._matches_filter(trace, ev_filter):
                            continue

                        # Apply sampling
                        if random.random() > sampling_rate:
                            continue
                        total_sampled += 1

                        # Skip traces with no output
                        if getattr(trace, "output", None) is None:
                            continue

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

                            total_evaluated += 1

                            # Attach score to Langfuse (idempotent via score_id)
                            if not dry_run:
                                score_id = self._make_score_id(trace.id, ev_name, since)
                                langfuse.create_score(
                                    score_id=score_id,
                                    trace_id=trace.id,
                                    name=ev_name,
                                    value=result["score"],
                                    data_type=evaluator.get("score_type", "NUMERIC"),
                                    comment=str(result.get("reasoning", ""))[
                                        :TRACE_CONTENT_MAX
                                    ],
                                )
                                total_scored += 1

                            # Audit log
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

                    # Page-based pagination — advance or stop
                    meta = getattr(traces_response, "meta", None)
                    total_pages = getattr(meta, "total_pages", 1) if meta else 1
                    if page >= total_pages or not traces:
                        break
                    page += 1

                print(f"  Evaluated: {total_evaluated} | Scored: {total_scored}")

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

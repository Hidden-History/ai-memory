"""BP-185 D6/D1: commented-default bounds + drift checks in check_env_completeness.

Covers the Gate-1 CI extension:
  - a bounds VIOLATION (commented value outside the field's ge/le) FAILS the
    gate (exit non-zero),
  - an in-bounds DRIFT (commented value != Field default) only WARNs and does
    NOT fail the gate.
"""

import check_env_completeness as cec
from check_env_completeness import check_commented_defaults, run_check

REAL_EXAMPLE = cec._repo_root / "docker" / ".env.example"


class TestCommentedDefaultClassification:
    """check_commented_defaults() splits findings into violations vs drifts."""

    def test_value_below_ge_is_violation_not_drift(self):
        # INJECTION_SCORE_GAP_THRESHOLD has ge=0.5; 0.15 is below the floor.
        violations, drifts = check_commented_defaults(
            {"INJECTION_SCORE_GAP_THRESHOLD": "0.15"}
        )
        assert violations, "value below ge must be a bounds violation"
        assert not drifts

    def test_in_bounds_int_drift_warns_not_fails(self):
        # LANGFUSE_TRACE_BUFFER_MAX_MB default=100 (ge=10, le=1000); 50 is in bounds.
        violations, drifts = check_commented_defaults(
            {"LANGFUSE_TRACE_BUFFER_MAX_MB": "50"}
        )
        assert not violations
        assert drifts, "in-bounds value != default must be a (non-failing) drift"

    def test_in_bounds_bool_drift_warns_not_fails(self):
        # LANGFUSE_SHOULD_EXPORT_SPAN default=True; false is a drift, no bounds.
        violations, drifts = check_commented_defaults(
            {"LANGFUSE_SHOULD_EXPORT_SPAN": "false"}
        )
        assert not violations
        assert drifts

    def test_value_matching_default_is_clean(self):
        violations, drifts = check_commented_defaults(
            {"INJECTION_SCORE_GAP_THRESHOLD": "0.7"}
        )
        assert not violations
        assert not drifts

    def test_non_schema_key_is_ignored(self):
        violations, drifts = check_commented_defaults({"NOT_A_REAL_FIELD": "123"})
        assert not violations
        assert not drifts


class TestRunCheckExitCodes:
    """run_check() converts a violation into exit 1 but a drift into exit 0."""

    def _mutated_example(self, tmp_path, old, new):
        text = REAL_EXAMPLE.read_text(encoding="utf-8")
        assert old in text, f"expected {old!r} present in real .env.example"
        dst = tmp_path / ".env.example"
        dst.write_text(text.replace(old, new), encoding="utf-8")
        return dst

    def test_clean_real_example_passes(self):
        assert run_check(REAL_EXAMPLE) == 0

    def test_out_of_bounds_commented_default_fails(self, tmp_path):
        mutated = self._mutated_example(
            tmp_path,
            "# INJECTION_SCORE_GAP_THRESHOLD=0.7",
            "# INJECTION_SCORE_GAP_THRESHOLD=0.15",
        )
        assert run_check(mutated) == 1

    def test_in_bounds_drift_does_not_fail(self, tmp_path, capsys):
        mutated = self._mutated_example(
            tmp_path,
            "# LANGFUSE_TRACE_BUFFER_MAX_MB=100",
            "# LANGFUSE_TRACE_BUFFER_MAX_MB=50",
        )
        rc = run_check(mutated)
        out = capsys.readouterr().out
        assert rc == 0
        assert "WARN" in out

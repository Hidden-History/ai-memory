"""Tests for scripts/create_datasets.py golden dataset definitions.

Validates:
  - All 5 datasets are defined
  - DS-04 has exactly as many items as keyword patterns in triggers.py
  - All items have required input/expected_output structure
  - No placeholder data ("TODO", "TBD", "example")
  - Idempotency logic (dry-run) works without Langfuse connection

PLAN-012 Phase 3 — Section 6.1
"""

import os
import sys
from typing import ClassVar

import pytest

# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------

# Add scripts/ to path for direct import
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")
SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")

sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))
sys.path.insert(0, os.path.abspath(SRC_DIR))


def _import_datasets_module():
    """Import create_datasets without executing main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "create_datasets",
        os.path.join(os.path.abspath(SCRIPTS_DIR), "create_datasets.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _import_triggers_module():
    """Import triggers.py to get the authoritative keyword counts."""
    import importlib.util

    triggers_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "memory", "triggers.py"
    )
    spec = importlib.util.spec_from_file_location(
        "triggers_for_test",
        os.path.abspath(triggers_path),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def datasets_mod():
    return _import_datasets_module()


@pytest.fixture(scope="module")
def triggers_mod():
    return _import_triggers_module()


# ---------------------------------------------------------------------------
# TC-1: All 5 datasets are defined
# ---------------------------------------------------------------------------


class TestDatasetCompleteness:
    EXPECTED_DATASET_NAMES: ClassVar[set[str]] = {
        "ds-01-retrieval-golden-set",
        "ds-02-error-pattern-match",
        "ds-03-bootstrap-round-trip",
        "ds-04-keyword-trigger-routing",
        "ds-05-chunking-quality",
    }

    def test_five_datasets_defined(self, datasets_mod):
        """DATASETS list must contain exactly 5 entries."""
        assert (
            len(datasets_mod.DATASETS) == 5
        ), f"Expected 5 datasets, got {len(datasets_mod.DATASETS)}"

    def test_all_expected_names_present(self, datasets_mod):
        """All 5 canonical dataset names must be present."""
        names = {ds["name"] for ds in datasets_mod.DATASETS}
        missing = self.EXPECTED_DATASET_NAMES - names
        assert not missing, f"Missing dataset names: {missing}"

    def test_each_dataset_has_required_keys(self, datasets_mod):
        """Each dataset entry must have name, description, metadata, items."""
        required_keys = {"name", "description", "metadata", "items"}
        for ds in datasets_mod.DATASETS:
            missing = required_keys - ds.keys()
            assert not missing, f"Dataset {ds.get('name', '?')} missing keys: {missing}"

    def test_each_dataset_metadata_has_version_and_created(self, datasets_mod):
        """Dataset metadata must include version, created, and project fields."""
        for ds in datasets_mod.DATASETS:
            meta = ds["metadata"]
            assert "version" in meta, f"{ds['name']} metadata missing 'version'"
            assert "created" in meta, f"{ds['name']} metadata missing 'created'"
            assert "project" in meta, f"{ds['name']} metadata missing 'project'"
            assert (
                meta["project"] == "ai-memory"
            ), f"{ds['name']} metadata project != 'ai-memory'"


# ---------------------------------------------------------------------------
# TC-2: DS-04 item count matches triggers.py keyword patterns exactly
# ---------------------------------------------------------------------------


class TestDS04KeywordCount:
    def _count_keyword_patterns(self, triggers_mod) -> int:
        """Count all keyword patterns across all TRIGGER_CONFIG entries."""
        config = triggers_mod.TRIGGER_CONFIG
        total = 0
        for _trigger_name, trigger_cfg in config.items():
            patterns = trigger_cfg.get("patterns", [])
            total += len(patterns)
        return total

    def test_ds04_item_count_matches_triggers(self, datasets_mod, triggers_mod):
        """DS-04 must have exactly as many items as keyword patterns in triggers.py."""
        ds04 = next(
            ds
            for ds in datasets_mod.DATASETS
            if ds["name"] == "ds-04-keyword-trigger-routing"
        )
        actual_item_count = len(ds04["items"])
        expected_count = self._count_keyword_patterns(triggers_mod)

        assert actual_item_count == expected_count, (
            f"DS-04 has {actual_item_count} items but triggers.py has "
            f"{expected_count} keyword patterns. "
            "Update DS_04_ITEMS to match triggers.py exactly."
        )

    def test_ds04_expected_68_items(self, datasets_mod):
        """DS-04 must have exactly 68 items (all keyword patterns in triggers.py TRIGGER_CONFIG).

        Count breakdown:
          error_detection:          5 patterns
          decision_keywords:       20 patterns
          session_history_keywords: 16 patterns
          best_practices_keywords: 27 patterns
          Total:                   68 patterns
        """
        ds04 = next(
            ds
            for ds in datasets_mod.DATASETS
            if ds["name"] == "ds-04-keyword-trigger-routing"
        )
        assert len(ds04["items"]) == 68, (
            f"DS-04 expected 68 items, got {len(ds04['items'])}. "
            "Recount all keyword patterns in triggers.py TRIGGER_CONFIG "
            "(includes error_detection, decision_keywords, session_history_keywords, best_practices_keywords)."
        )

    def test_ds04_covers_all_four_trigger_types(self, datasets_mod):
        """DS-04 must cover all 4 keyword-bearing trigger types from triggers.py."""
        ds04 = next(
            ds
            for ds in datasets_mod.DATASETS
            if ds["name"] == "ds-04-keyword-trigger-routing"
        )
        triggers_present = {
            item["expected_output"]["expected_trigger"] for item in ds04["items"]
        }
        expected_triggers = {
            "error_detection",
            "decision_keywords",
            "session_history_keywords",
            "best_practices_keywords",
        }
        missing = expected_triggers - triggers_present
        assert not missing, f"DS-04 missing trigger types: {missing}"

    def test_ds04_trigger_distribution(self, datasets_mod):
        """DS-04 trigger distribution must match patterns in triggers.py."""
        ds04 = next(
            ds
            for ds in datasets_mod.DATASETS
            if ds["name"] == "ds-04-keyword-trigger-routing"
        )
        from collections import Counter

        counts = Counter(
            item["expected_output"]["expected_trigger"] for item in ds04["items"]
        )
        assert (
            counts["error_detection"] == 5
        ), f"Expected 5 error_detection items, got {counts['error_detection']}"
        assert (
            counts["decision_keywords"] == 20
        ), f"Expected 20 decision_keywords items, got {counts['decision_keywords']}"
        assert (
            counts["session_history_keywords"] == 16
        ), f"Expected 16 session_history_keywords items, got {counts['session_history_keywords']}"
        assert (
            counts["best_practices_keywords"] == 27
        ), f"Expected 27 best_practices_keywords items, got {counts['best_practices_keywords']}"


# ---------------------------------------------------------------------------
# TC-3: All items have required input/expected_output structure
# ---------------------------------------------------------------------------


class TestItemStructure:
    def test_all_items_have_input_and_expected_output(self, datasets_mod):
        """Every dataset item must have 'input' and 'expected_output' keys."""
        for ds in datasets_mod.DATASETS:
            for i, item in enumerate(ds["items"]):
                assert "input" in item, f"{ds['name']} item[{i}] missing 'input' key"
                assert (
                    "expected_output" in item
                ), f"{ds['name']} item[{i}] missing 'expected_output' key"

    def test_ds01_items_have_query_collection_type_filter(self, datasets_mod):
        """DS-01 items must have query, collection, and type_filter in input."""
        ds01 = next(
            ds
            for ds in datasets_mod.DATASETS
            if ds["name"] == "ds-01-retrieval-golden-set"
        )
        for i, item in enumerate(ds01["items"]):
            inp = item["input"]
            assert "query" in inp, f"DS-01 item[{i}] input missing 'query'"
            assert "collection" in inp, f"DS-01 item[{i}] input missing 'collection'"
            assert "type_filter" in inp, f"DS-01 item[{i}] input missing 'type_filter'"

    def test_ds01_items_have_should_match_and_min_relevance(self, datasets_mod):
        """DS-01 items must have should_match and min_relevance >= 0.6 in expected_output."""
        ds01 = next(
            ds
            for ds in datasets_mod.DATASETS
            if ds["name"] == "ds-01-retrieval-golden-set"
        )
        for i, item in enumerate(ds01["items"]):
            out = item["expected_output"]
            assert (
                "should_match" in out
            ), f"DS-01 item[{i}] expected_output missing 'should_match'"
            assert (
                "min_relevance" in out
            ), f"DS-01 item[{i}] expected_output missing 'min_relevance'"
            assert (
                out["min_relevance"] >= 0.6
            ), f"DS-01 item[{i}] min_relevance {out['min_relevance']} < 0.6"

    def test_ds01_covers_all_five_collections(self, datasets_mod):
        """DS-01 must have at least 3 items per collection across all 5 collections."""
        ds01 = next(
            ds
            for ds in datasets_mod.DATASETS
            if ds["name"] == "ds-01-retrieval-golden-set"
        )
        from collections import Counter

        collection_counts = Counter(
            item["input"]["collection"] for item in ds01["items"]
        )
        required_collections = {
            "code-patterns",
            "conventions",
            "discussions",
            "github",
            "jira-data",
        }
        for col in required_collections:
            assert col in collection_counts, f"DS-01 missing collection: {col}"
            assert (
                collection_counts[col] >= 3
            ), f"DS-01 collection {col!r} has only {collection_counts[col]} items (need >= 3)"

    def test_ds01_item_count_in_range(self, datasets_mod):
        """DS-01 must have 20-30 items."""
        ds01 = next(
            ds
            for ds in datasets_mod.DATASETS
            if ds["name"] == "ds-01-retrieval-golden-set"
        )
        count = len(ds01["items"])
        assert 20 <= count <= 30, f"DS-01 has {count} items (expected 20-30)"

    def test_ds02_items_have_error_message_and_language(self, datasets_mod):
        """DS-02 items must have error_message and language in input."""
        ds02 = next(
            ds
            for ds in datasets_mod.DATASETS
            if ds["name"] == "ds-02-error-pattern-match"
        )
        for i, item in enumerate(ds02["items"]):
            inp = item["input"]
            assert (
                "error_message" in inp
            ), f"DS-02 item[{i}] input missing 'error_message'"
            assert "language" in inp, f"DS-02 item[{i}] input missing 'language'"

    def test_ds02_covers_python_javascript_bash(self, datasets_mod):
        """DS-02 must cover python, javascript, and bash error patterns."""
        ds02 = next(
            ds
            for ds in datasets_mod.DATASETS
            if ds["name"] == "ds-02-error-pattern-match"
        )
        languages = {item["input"]["language"] for item in ds02["items"]}
        assert "python" in languages, "DS-02 missing python errors"
        assert "javascript" in languages, "DS-02 missing javascript errors"
        assert "bash" in languages, "DS-02 missing bash errors"

    def test_ds02_item_count_in_range(self, datasets_mod):
        """DS-02 must have 10-15 items."""
        ds02 = next(
            ds
            for ds in datasets_mod.DATASETS
            if ds["name"] == "ds-02-error-pattern-match"
        )
        count = len(ds02["items"])
        assert 10 <= count <= 15, f"DS-02 has {count} items (expected 10-15)"

    def test_ds03_items_have_agent_id_parzival(self, datasets_mod):
        """DS-03 items must have agent_id='parzival' for tenant isolation."""
        ds03 = next(
            ds
            for ds in datasets_mod.DATASETS
            if ds["name"] == "ds-03-bootstrap-round-trip"
        )
        for i, item in enumerate(ds03["items"]):
            assert (
                item["input"].get("agent_id") == "parzival"
            ), f"DS-03 item[{i}] must have agent_id='parzival'"
            assert (
                item["expected_output"].get("agent_id") == "parzival"
            ), f"DS-03 item[{i}] expected_output must have agent_id='parzival'"

    def test_ds03_item_count_in_range(self, datasets_mod):
        """DS-03 must have 5-10 items."""
        ds03 = next(
            ds
            for ds in datasets_mod.DATASETS
            if ds["name"] == "ds-03-bootstrap-round-trip"
        )
        count = len(ds03["items"])
        assert 5 <= count <= 10, f"DS-03 has {count} items (expected 5-10)"

    def test_ds04_items_have_user_prompt_input(self, datasets_mod):
        """DS-04 items must have user_prompt in input."""
        ds04 = next(
            ds
            for ds in datasets_mod.DATASETS
            if ds["name"] == "ds-04-keyword-trigger-routing"
        )
        for i, item in enumerate(ds04["items"]):
            assert (
                "user_prompt" in item["input"]
            ), f"DS-04 item[{i}] input missing 'user_prompt'"

    def test_ds04_items_have_expected_trigger_and_collection(self, datasets_mod):
        """DS-04 items must have expected_trigger and expected_collection in expected_output."""
        ds04 = next(
            ds
            for ds in datasets_mod.DATASETS
            if ds["name"] == "ds-04-keyword-trigger-routing"
        )
        for i, item in enumerate(ds04["items"]):
            out = item["expected_output"]
            assert (
                "expected_trigger" in out
            ), f"DS-04 item[{i}] expected_output missing 'expected_trigger'"
            assert (
                "expected_collection" in out
            ), f"DS-04 item[{i}] expected_output missing 'expected_collection'"

    def test_ds05_items_have_content_and_content_type(self, datasets_mod):
        """DS-05 items must have content and content_type in input."""
        ds05 = next(
            ds for ds in datasets_mod.DATASETS if ds["name"] == "ds-05-chunking-quality"
        )
        for i, item in enumerate(ds05["items"]):
            inp = item["input"]
            assert "content" in inp, f"DS-05 item[{i}] input missing 'content'"
            assert (
                "content_type" in inp
            ), f"DS-05 item[{i}] input missing 'content_type'"

    def test_ds05_items_have_chunk_count_and_strategy(self, datasets_mod):
        """DS-05 items must have expected_chunk_count and chunk_strategy in expected_output."""
        ds05 = next(
            ds for ds in datasets_mod.DATASETS if ds["name"] == "ds-05-chunking-quality"
        )
        for i, item in enumerate(ds05["items"]):
            out = item["expected_output"]
            assert (
                "expected_chunk_count" in out
            ), f"DS-05 item[{i}] expected_output missing 'expected_chunk_count'"
            assert (
                "chunk_strategy" in out
            ), f"DS-05 item[{i}] expected_output missing 'chunk_strategy'"

    def test_ds05_item_count(self, datasets_mod):
        """DS-05 must have exactly 10 items."""
        ds05 = next(
            ds for ds in datasets_mod.DATASETS if ds["name"] == "ds-05-chunking-quality"
        )
        assert (
            len(ds05["items"]) == 10
        ), f"DS-05 has {len(ds05['items'])} items (expected 10)"


# ---------------------------------------------------------------------------
# TC-4: No placeholder data
# ---------------------------------------------------------------------------


class TestNoPlaceholderData:
    # "example" excluded: appears legitimately in filenames (.env.example, README etc.)
    PLACEHOLDER_STRINGS: ClassVar[set[str]] = {
        "TODO",
        "TBD",
        "placeholder",
        "FIXME",
        "PLACEHOLDER",
    }

    def _flatten_value(self, val) -> list[str]:
        """Recursively flatten a value into a list of strings for scanning."""
        if isinstance(val, str):
            return [val]
        if isinstance(val, dict):
            result = []
            for v in val.values():
                result.extend(self._flatten_value(v))
            return result
        if isinstance(val, list):
            result = []
            for v in val:
                result.extend(self._flatten_value(v))
            return result
        return []

    def test_no_placeholder_in_inputs(self, datasets_mod):
        """No item input must contain development placeholder strings.

        Check is case-sensitive: 'TODO' flags a placeholder but 'todo' is a
        natural English word that legitimately appears in keyword trigger prompts
        (e.g., the 'todo' session_history_keywords trigger pattern).
        """
        import re

        for ds in datasets_mod.DATASETS:
            for i, item in enumerate(ds["items"]):
                strings = self._flatten_value(item["input"])
                for s in strings:
                    for placeholder in self.PLACEHOLDER_STRINGS:
                        # Case-sensitive word-boundary check — avoids false positives on natural
                        # words like 'todo' (session history trigger) or filenames like '.env.example'
                        if re.search(rf"\b{re.escape(placeholder)}\b", s):
                            pytest.fail(
                                f"{ds['name']} item[{i}] input contains placeholder {placeholder!r}: {s[:100]!r}"
                            )

    def test_no_placeholder_in_expected_outputs(self, datasets_mod):
        """No item expected_output must contain development placeholder strings."""
        import re

        for ds in datasets_mod.DATASETS:
            for i, item in enumerate(ds["items"]):
                strings = self._flatten_value(item["expected_output"])
                for s in strings:
                    for placeholder in self.PLACEHOLDER_STRINGS:
                        if re.search(rf"\b{re.escape(placeholder)}\b", s):
                            pytest.fail(
                                f"{ds['name']} item[{i}] expected_output contains placeholder {placeholder!r}: {s[:100]!r}"
                            )

    def test_no_empty_strings_in_critical_fields(self, datasets_mod):
        """Critical string fields must not be empty."""
        ds01 = next(
            ds
            for ds in datasets_mod.DATASETS
            if ds["name"] == "ds-01-retrieval-golden-set"
        )
        for i, item in enumerate(ds01["items"]):
            assert item["input"]["query"].strip(), f"DS-01 item[{i}] has empty query"
            assert item["expected_output"][
                "should_match"
            ].strip(), f"DS-01 item[{i}] has empty should_match"

        ds04 = next(
            ds
            for ds in datasets_mod.DATASETS
            if ds["name"] == "ds-04-keyword-trigger-routing"
        )
        for i, item in enumerate(ds04["items"]):
            assert item["input"][
                "user_prompt"
            ].strip(), f"DS-04 item[{i}] has empty user_prompt"


# ---------------------------------------------------------------------------
# TC-5: Idempotency — dry-run mode works without Langfuse connection
# ---------------------------------------------------------------------------


class TestIdempotencyAndDryRun:
    def test_dry_run_returns_zero_exit_code(self, datasets_mod, capsys):
        """dry_run=True must return exit code 0 without calling Langfuse."""
        result = datasets_mod.create_all_datasets(dry_run=True)
        assert result == 0

    def test_dry_run_prints_all_five_datasets(self, datasets_mod, capsys):
        """dry_run output must mention all 5 dataset names."""
        datasets_mod.create_all_datasets(dry_run=True)
        captured = capsys.readouterr()
        output = captured.out
        for ds in datasets_mod.DATASETS:
            assert (
                ds["name"] in output
            ), f"dry_run output missing dataset name: {ds['name']}"

    def test_dry_run_prints_dry_run_marker(self, datasets_mod, capsys):
        """dry_run output must contain [DRY RUN] marker."""
        datasets_mod.create_all_datasets(dry_run=True)
        captured = capsys.readouterr()
        assert "[DRY RUN]" in captured.out

    def test_datasets_list_is_not_empty(self, datasets_mod):
        """DATASETS must not be an empty list."""
        assert len(datasets_mod.DATASETS) > 0

    def test_all_item_lists_are_non_empty(self, datasets_mod):
        """Every dataset must have at least one item."""
        for ds in datasets_mod.DATASETS:
            assert len(ds["items"]) > 0, f"Dataset {ds['name']} has no items"


# ---------------------------------------------------------------------------
# TC-6: V3 SDK compliance — no Langfuse() constructor with explicit creds
# ---------------------------------------------------------------------------


class TestV3SDKCompliance:
    def test_script_has_v3_header_comment(self):
        """create_datasets.py must have the V3 SDK header comment."""
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "create_datasets.py"
        )
        with open(os.path.abspath(script_path)) as f:
            content = f.read()
        assert (
            "V3 SDK ONLY" in content
        ), "create_datasets.py missing V3 SDK header comment"
        assert (
            "LANGFUSE-INTEGRATION-SPEC.md" in content
        ), "create_datasets.py missing LANGFUSE-INTEGRATION-SPEC.md reference"

    def test_no_langfuse_constructor_with_explicit_creds(self):
        """create_datasets.py must not import or call Langfuse() with explicit credentials.

        The check scans only executable code lines, not data/comment strings, to avoid
        false positives where dataset items contain documentation about V2 anti-patterns.
        """
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "create_datasets.py"
        )
        with open(os.path.abspath(script_path)) as f:
            lines = f.readlines()

        import re

        # Only scan lines that are actual code (not inside triple-quoted strings or pure comments)
        # Simple heuristic: skip lines where the Langfuse(...) match is inside a string literal
        # that starts with quotes (i.e., data lines inside dict/list literals)
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip comment-only lines
            if stripped.startswith("#"):
                continue
            # Skip lines that are entirely string content (data literals starting with quotes)
            if stripped.startswith('"') or stripped.startswith("'"):
                continue
            # Check for forbidden Langfuse() constructor with explicit creds in code
            if re.search(r"\bLangfuse\s*\(\s*(public_key|secret_key|host)\s*=", line):
                pytest.fail(
                    f"create_datasets.py line {lineno} uses Langfuse() constructor "
                    f"with explicit credentials (forbidden — use get_client() instead):\n  {line.rstrip()}"
                )

    def test_uses_get_client(self):
        """create_datasets.py must use get_client() (V3 singleton pattern)."""
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "create_datasets.py"
        )
        with open(os.path.abspath(script_path)) as f:
            content = f.read()
        assert "get_client" in content, "create_datasets.py missing get_client() call"

    def test_uses_flush(self):
        """create_datasets.py must call langfuse.flush() before exit."""
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "create_datasets.py"
        )
        with open(os.path.abspath(script_path)) as f:
            content = f.read()
        assert (
            "langfuse.flush()" in content
        ), "create_datasets.py missing langfuse.flush() call"

"""Unit tests for PLAN-028 P1 — conventions project-scoping.

Coverage:
- P1-1: store_best_practice / retrieve_best_practices require an explicit project
        group_id and fail loud (ValueError) when it is absent or empty
        (DEC-PM298-D4 — no cwd/os.getcwd()/detect_project fallback)
- P1-1: route_collections — conventions is project-scoped (shared=False)
- P1-1: search_both_collections applies group_id to conventions
- P1-3 RC-A: sys.path bootstrap present in aim-best-practices-researcher/SKILL.md;
             the skill passes an explicit group_id from AI_MEMORY_PROJECT_ID
- P1-3 RC-B: MemoryConfig() constructs when GITHUB_SYNC_ENABLED=true with missing creds;
             github_sync_usable is False; no ValueError raised

PLAN-028 P1 (W-01): FR16 amended — conventions is project-scoped.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# P1-1: store_best_practice — project-scoped storage
# ---------------------------------------------------------------------------


def _mock_storage(memory_id="mem-001", group_id="my-project"):
    """Return a patched MemoryStorage whose store_memory returns a stored result."""
    mock_storage = MagicMock()
    mock_storage.store_memory.return_value = {
        "status": "stored",
        "memory_id": memory_id,
        "group_id": group_id,
        "embedding_status": "complete",
    }
    return mock_storage


class TestStoreBestPracticeProjectScoped:
    """Unit tests for store_best_practice() project-scoping (P1-1, DEC-PM298-D4)."""

    def test_store_best_practice_requires_explicit_group_id(self):
        """Calling without group_id fails loud with ValueError (DEC-PM298-D4)."""
        from memory.storage import store_best_practice

        with pytest.raises(ValueError, match="explicit project scope"):
            store_best_practice(
                content="Always use type hints in Python 3.10+",
                session_id="test-session",
            )

    def test_store_best_practice_empty_group_id_raises(self):
        """An empty/whitespace group_id is rejected — no silent fallback."""
        from memory.storage import store_best_practice

        for bad in ("", "   "):
            with pytest.raises(ValueError, match="explicit project scope"):
                store_best_practice(
                    content="Use dependency injection for testability",
                    session_id="test-session",
                    group_id=bad,
                )

    def test_store_best_practice_no_cwd_parameter(self):
        """store_best_practice no longer exposes a cwd parameter (DEC-PM298-D4)."""
        import inspect

        from memory.storage import store_best_practice

        assert (
            "cwd" not in inspect.signature(store_best_practice).parameters
        ), "cwd param must be removed — project scope is required-explicit via group_id"

    def test_store_best_practice_does_not_hardcode_shared_group_id(self):
        """store_best_practice forwards the caller's group_id, never 'shared'."""
        with patch("memory.storage.MemoryStorage") as mock_storage_cls:
            mock_storage_cls.return_value = _mock_storage(group_id="my-project")

            from memory.storage import store_best_practice

            store_best_practice(
                content="Use dependency injection for testability",
                session_id="test-session",
                group_id="my-project",
            )

            call_kwargs = mock_storage_cls.return_value.store_memory.call_args[1]
            assert (
                call_kwargs.get("group_id") != "shared"
            ), "store_best_practice must not hardcode group_id='shared'"
            # cwd passed to store_memory is unused for scoping (not the old sentinel)
            assert (
                call_kwargs.get("cwd") != "/__best_practices__"
            ), "the old '/__best_practices__' sentinel path must not be used"

    def test_store_best_practice_explicit_group_id_forwarded(self):
        """An explicit group_id is forwarded to store_memory unchanged."""
        with patch("memory.storage.MemoryStorage") as mock_storage_cls:
            mock_storage_cls.return_value = _mock_storage(group_id="explicit-project")

            from memory.storage import store_best_practice

            store_best_practice(
                content="Prefer explicit over implicit dependencies",
                session_id="test-session",
                group_id="explicit-project",
            )

            call_kwargs = mock_storage_cls.return_value.store_memory.call_args[1]
            assert call_kwargs["group_id"] == "explicit-project"

    def test_store_best_practice_result_does_not_override_group_id(self):
        """The 'shared' override of result['group_id'] is removed in P1."""
        with patch("memory.storage.MemoryStorage") as mock_storage_cls:
            mock_storage_cls.return_value = _mock_storage(group_id="real-project")

            from memory.storage import store_best_practice

            result = store_best_practice(
                content="Capture domain logic in plain Python, not ORM tricks",
                session_id="test-session",
                group_id="real-project",
            )

            # The pre-P1 code forced result["group_id"] = "shared".
            # Post-P1 the result must preserve the real group_id from store_memory.
            assert result["group_id"] == "real-project"
            assert result["group_id"] != "shared"

    def test_store_best_practice_collection_always_conventions(self):
        """collection field is always 'conventions' regardless of group_id."""
        with patch("memory.storage.MemoryStorage") as mock_storage_cls:
            mock_storage_cls.return_value = _mock_storage(group_id="any-project")

            from memory.storage import store_best_practice

            result = store_best_practice(
                content="Use structured logging with contextual fields",
                session_id="test-session",
                group_id="any-project",
            )

            assert result["collection"] == "conventions"


# ---------------------------------------------------------------------------
# P1-1: retrieve_best_practices — project-scoped retrieval
# ---------------------------------------------------------------------------


class TestRetrieveBestPracticesProjectScoped:
    """Unit tests for retrieve_best_practices() project-scoping (P1-1, DEC-PM298-D4)."""

    def test_retrieve_requires_explicit_group_id(self):
        """Calling without group_id fails loud with ValueError (DEC-PM298-D4)."""
        from memory.search import retrieve_best_practices

        with pytest.raises(ValueError, match="explicit project scope"):
            retrieve_best_practices(query="Python best practices")

    def test_retrieve_empty_group_id_raises(self):
        """An empty/whitespace group_id is rejected — no silent fallback."""
        from memory.search import retrieve_best_practices

        for bad in ("", "   "):
            with pytest.raises(ValueError, match="explicit project scope"):
                retrieve_best_practices(query="test query", group_id=bad)

    def test_retrieve_no_cwd_parameter(self):
        """retrieve_best_practices no longer exposes a cwd parameter (DEC-PM298-D4)."""
        import inspect

        from memory.search import retrieve_best_practices

        assert (
            "cwd" not in inspect.signature(retrieve_best_practices).parameters
        ), "cwd param must be removed — project scope is required-explicit via group_id"

    def test_retrieve_applies_group_id_filter(self):
        """retrieve_best_practices passes the explicit group_id to search()."""
        with patch("memory.search.MemorySearch") as mock_cls:
            mock_inst = MagicMock()
            mock_cls.return_value = mock_inst
            mock_inst.search.return_value = []

            from memory.search import retrieve_best_practices

            retrieve_best_practices(
                query="Python best practices",
                group_id="my-project",
            )

            call_kwargs = mock_inst.search.call_args[1]
            assert (
                call_kwargs["group_id"] == "my-project"
            ), "retrieve_best_practices must pass the explicit group_id to search()"

    def test_retrieve_does_not_force_none_group_id(self):
        """retrieve_best_practices must not override the caller's group_id to None."""
        with patch("memory.search.MemorySearch") as mock_cls:
            mock_inst = MagicMock()
            mock_cls.return_value = mock_inst
            mock_inst.search.return_value = []

            from memory.search import retrieve_best_practices

            retrieve_best_practices(query="test query", group_id="project-xyz")

            call_kwargs = mock_inst.search.call_args[1]
            assert (
                call_kwargs["group_id"] is not None
            ), "retrieve_best_practices must not force group_id=None (old cross-project behavior)"
            assert call_kwargs["group_id"] == "project-xyz"


# ---------------------------------------------------------------------------
# P1-1: route_collections — conventions is project-scoped
# ---------------------------------------------------------------------------


class TestRouteCollectionsProjectScoped:
    """Unit tests for route_collections() — conventions no longer shared (P1-1)."""

    def test_route_conventions_shared_is_false(self):
        """All RouteTarget items for conventions must have shared=False."""
        with (
            patch("memory.injection.detect_decision_keywords", return_value=False),
            patch(
                "memory.injection.detect_session_history_keywords", return_value=False
            ),
            patch("memory.injection.detect_best_practices_keywords", return_value=True),
        ):
            from memory.injection import route_collections

            routes = route_collections("what are the best practices for Python?")

        conventions_routes = [r for r in routes if r.collection == "conventions"]
        assert len(conventions_routes) > 0, "Should have at least one conventions route"
        for route in conventions_routes:
            assert (
                route.shared is False
            ), f"conventions RouteTarget.shared must be False after P1, got {route.shared}"

    def test_route_unknown_intent_conventions_shared_false(self):
        """Unknown-intent cascade includes conventions with shared=False."""
        with (
            patch("memory.injection.detect_decision_keywords", return_value=False),
            patch(
                "memory.injection.detect_session_history_keywords", return_value=False
            ),
            patch(
                "memory.injection.detect_best_practices_keywords", return_value=False
            ),
            patch("memory.injection._FILE_PATH_RE") as mock_re,
            patch("memory.injection.detect_intent") as mock_intent,
        ):
            mock_re.search.return_value = None
            from memory.injection import IntentType

            mock_intent.return_value = IntentType.UNKNOWN

            from memory.injection import route_collections

            routes = route_collections("something completely unknown")

        conventions_routes = [r for r in routes if r.collection == "conventions"]
        assert len(conventions_routes) > 0
        for route in conventions_routes:
            assert (
                route.shared is False
            ), f"conventions in cascade must have shared=False, got {route.shared}"

    def test_no_route_has_shared_true(self):
        """No RouteTarget produced by route_collections should have shared=True."""
        with (
            patch("memory.injection.detect_decision_keywords", return_value=False),
            patch(
                "memory.injection.detect_session_history_keywords", return_value=False
            ),
            patch(
                "memory.injection.detect_best_practices_keywords", return_value=False
            ),
            patch("memory.injection._FILE_PATH_RE") as mock_re,
            patch("memory.injection.detect_intent") as mock_intent,
        ):
            mock_re.search.return_value = None
            from memory.injection import IntentType

            mock_intent.return_value = IntentType.UNKNOWN

            from memory.injection import route_collections

            routes = route_collections("anything")

        assert all(
            not r.shared for r in routes
        ), "No RouteTarget should have shared=True after PLAN-028 P1"


# ---------------------------------------------------------------------------
# P1-3 RC-A: sys.path bootstrap in aim-best-practices-researcher/SKILL.md
# ---------------------------------------------------------------------------


class TestSkillMdSysPathBootstrap:
    """Verify sys.path bootstrap is present in SKILL.md Python blocks (RC-A)."""

    _SKILL_MD_PATH = (
        Path(__file__).parent.parent
        / "_ai-memory"
        / "skills"
        / "aim-best-practices-researcher"
        / "SKILL.md"
    )

    def _read_skill_md(self) -> str:
        assert (
            self._SKILL_MD_PATH.exists()
        ), f"SKILL.md not found at {self._SKILL_MD_PATH}"
        return self._SKILL_MD_PATH.read_text()

    def test_skill_md_contains_sys_path_bootstrap(self):
        """SKILL.md must contain sys.path.insert bootstrap before memory imports."""
        content = self._read_skill_md()
        assert (
            'sys.path.insert(0, os.path.join(os.path.expanduser("~/.ai-memory"), "src"))'
            in content
        ), "RC-A fix missing: sys.path bootstrap not found in SKILL.md Python blocks"

    def test_skill_md_bootstrap_appears_before_memory_import(self):
        """sys.path bootstrap must appear before 'from memory.' imports in SKILL.md."""
        content = self._read_skill_md()
        bootstrap = 'sys.path.insert(0, os.path.join(os.path.expanduser("~/.ai-memory"), "src"))'
        memory_import = "from memory."

        bootstrap_idx = content.find(bootstrap)
        memory_import_idx = content.find(memory_import)

        assert bootstrap_idx != -1, "Bootstrap not found in SKILL.md"
        assert memory_import_idx != -1, "'from memory.' not found in SKILL.md"
        assert (
            bootstrap_idx < memory_import_idx
        ), "sys.path bootstrap must appear BEFORE the first 'from memory.' import in SKILL.md"

    def test_skill_md_phase4_passes_explicit_group_id(self):
        """Phase 4 store block must pass an explicit group_id, never cwd=os.getcwd().

        DEC-PM298-D4: project scope is required-explicit. The skill resolves the
        project deterministically from AI_MEMORY_PROJECT_ID and passes it as
        group_id — os.getcwd() is unreliable for this forked skill subprocess.
        """
        content = self._read_skill_md()
        assert "cwd=os.getcwd()" not in content, (
            "SKILL.md must NOT pass cwd=os.getcwd() — that is the contamination "
            "vector DEC-PM298-D4 removes"
        )
        assert (
            "group_id=project_id" in content
        ), "Phase 4 Python block must pass an explicit group_id to store_best_practice()"
        assert (
            'os.environ.get("AI_MEMORY_PROJECT_ID")' in content
        ), "SKILL.md must resolve project scope from AI_MEMORY_PROJECT_ID"

    def test_skill_md_no_sentinel_path(self):
        """SKILL.md must not reference the old '/__best_practices__' sentinel path."""
        content = self._read_skill_md()
        assert (
            "/__best_practices__" not in content
        ), "Old sentinel path '/__best_practices__' must not appear in SKILL.md after P1"


# ---------------------------------------------------------------------------
# P1-3 RC-B: MemoryConfig() succeeds when GITHUB_SYNC_ENABLED=true + bad creds
# ---------------------------------------------------------------------------


class TestMemoryConfigGithubDecoupling:
    """Unit tests for RC-B — validate_github_config no longer raises ValueError.

    NOTE: MemoryConfig is a pydantic-settings BaseSettings with env_ignore_empty=True.
    Empty monkeypatch env vars are ignored in favour of the real .env values.
    Tests that need to control specific field values call the validator directly
    on a mock instance rather than constructing the full config.
    """

    def test_memory_config_constructs_without_raising(self):
        """MemoryConfig() must construct without raising ValueError.

        RC-B primary fix: the validator no longer raises — construction must
        succeed even if GitHub creds are missing or incomplete.
        """
        try:
            from memory.config import MemoryConfig

            cfg = MemoryConfig()
            # Key assertion: github_sync_usable field is present and is a bool
            assert isinstance(
                cfg.github_sync_usable, bool
            ), "github_sync_usable must be a bool field on MemoryConfig"
        except ValueError as e:
            pytest.fail(
                f"MemoryConfig() must not raise ValueError (RC-B fix missing): {e}"
            )

    def test_validator_sets_usable_false_on_empty_token(self):
        """validate_github_config sets github_sync_usable=False when token is empty."""
        from pydantic import SecretStr

        from memory.config import MemoryConfig

        # Test the validator method directly on a mock object to control field values
        # without going through BaseSettings env loading (env_ignore_empty=True would
        # otherwise suppress our empty-string overrides).
        mock_self = MagicMock()
        mock_self.github_sync_enabled = True
        mock_self.github_token = SecretStr("")
        mock_self.github_repo = "owner/repo"

        # Must NOT raise ValueError (pre-P1 would have raised)
        try:
            MemoryConfig.validate_github_config(mock_self)
        except ValueError as e:
            pytest.fail(
                f"validate_github_config must not raise for empty token "
                f"(RC-B fix missing): {e}"
            )

        # FIX-9: assert what the test name claims — the derived flag is False.
        assert (
            mock_self.github_sync_usable is False
        ), "github_sync_usable must be False when the token is empty"

    def test_validator_sets_usable_false_on_no_slash_repo(self):
        """validate_github_config sets github_sync_usable=False when repo lacks owner/."""
        from pydantic import SecretStr

        from memory.config import MemoryConfig

        mock_self = MagicMock()
        mock_self.github_sync_enabled = True
        mock_self.github_token = SecretStr("ghp_validtoken")
        mock_self.github_repo = "noslash"  # missing the slash

        # Must NOT raise ValueError (pre-P1 would have raised)
        try:
            MemoryConfig.validate_github_config(mock_self)
        except ValueError as e:
            pytest.fail(
                f"validate_github_config must not raise for malformed repo "
                f"(RC-B fix missing): {e}"
            )

        # FIX-9: assert what the test name claims — the derived flag is False.
        assert (
            mock_self.github_sync_usable is False
        ), "github_sync_usable must be False when the repo lacks owner/ format"

    def test_validator_sets_usable_false_on_empty_repo(self):
        """validate_github_config does not raise when repo is empty."""
        from pydantic import SecretStr

        from memory.config import MemoryConfig

        mock_self = MagicMock()
        mock_self.github_sync_enabled = True
        mock_self.github_token = SecretStr("ghp_validtoken")
        mock_self.github_repo = ""  # empty

        try:
            MemoryConfig.validate_github_config(mock_self)
        except ValueError as e:
            pytest.fail(
                f"validate_github_config must not raise for empty repo "
                f"(RC-B fix missing): {e}"
            )

        # FIX-9: assert what the test name claims — the derived flag is False.
        assert (
            mock_self.github_sync_usable is False
        ), "github_sync_usable must be False when the repo is empty"

    def test_validator_emits_warning_when_creds_incomplete(self, caplog):
        """FIX-8: validate_github_config logs the github_sync_not_usable warning.

        RC-B downgrades the former hard ValueError to a warning; this asserts the
        warning is actually emitted (and not silently swallowed) when sync is
        enabled but the credentials are incomplete.
        """
        import logging

        from pydantic import SecretStr

        from memory.config import MemoryConfig

        mock_self = MagicMock()
        mock_self.github_sync_enabled = True
        mock_self.github_token = SecretStr("")  # missing token
        mock_self.github_repo = ""  # missing repo

        with caplog.at_level(logging.WARNING, logger="memory.config"):
            MemoryConfig.validate_github_config(mock_self)

        assert any(
            "github_sync_not_usable" in rec.getMessage() for rec in caplog.records
        ), "validate_github_config must emit the github_sync_not_usable warning"
        assert mock_self.github_sync_usable is False

    def test_validator_no_warning_when_creds_complete(self, caplog):
        """FIX-8 (complement): no github_sync_not_usable warning when creds are valid."""
        import logging

        from pydantic import SecretStr

        from memory.config import MemoryConfig

        mock_self = MagicMock()
        mock_self.github_sync_enabled = True
        mock_self.github_token = SecretStr("ghp_validtoken")
        mock_self.github_repo = "owner/repo"

        with caplog.at_level(logging.WARNING, logger="memory.config"):
            MemoryConfig.validate_github_config(mock_self)

        assert not any(
            "github_sync_not_usable" in rec.getMessage() for rec in caplog.records
        ), "no warning expected when GitHub credentials are complete"
        assert mock_self.github_sync_usable is True

    def test_memory_config_has_github_sync_usable_field(self):
        """MemoryConfig must have a github_sync_usable field (RC-B derived flag)."""
        from memory.config import MemoryConfig

        cfg = MemoryConfig()
        assert hasattr(
            cfg, "github_sync_usable"
        ), "github_sync_usable field missing from MemoryConfig (RC-B fix not applied)"
        assert isinstance(cfg.github_sync_usable, bool)

    def test_memory_config_github_sync_usable_false_when_disabled(self, monkeypatch):
        """github_sync_usable is False when GITHUB_SYNC_ENABLED=false."""
        monkeypatch.setenv("GITHUB_SYNC_ENABLED", "false")

        from memory.config import MemoryConfig

        cfg = MemoryConfig()
        assert cfg.github_sync_usable is False

    def test_store_best_practice_unblocked_by_github_config(self, monkeypatch):
        """store_best_practice must succeed even when GitHub creds are misconfigured.

        This is the end-to-end RC-B regression test: before the fix,
        MemoryConfig() construction failed, making store_best_practice unusable
        when GITHUB_SYNC_ENABLED=true with incomplete creds.
        """
        monkeypatch.setenv("GITHUB_SYNC_ENABLED", "true")

        with (patch("memory.storage.MemoryStorage") as mock_storage_cls,):
            mock_storage = MagicMock()
            mock_storage_cls.return_value = mock_storage
            mock_storage.store_memory.return_value = {
                "status": "stored",
                "memory_id": "mem-rc-b",
                "group_id": "test-proj",
                "embedding_status": "complete",
            }

            from memory.storage import store_best_practice

            # Must not raise — RC-B fix decouples GitHub config from storage.
            # An explicit group_id is supplied (DEC-PM298-D4): this test isolates
            # the GitHub-config path, so project scope must be provided normally.
            try:
                result = store_best_practice(
                    content="RC-B regression test: storage must work without GitHub creds",
                    session_id="rc-b-session",
                    group_id="rc-b-project",
                )
                assert result["status"] in ["stored", "duplicate"]
            except ValueError as e:
                pytest.fail(
                    f"store_best_practice must not raise ValueError due to GitHub config "
                    f"(RC-B regression): {e}"
                )

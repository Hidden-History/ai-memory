"""Tests for project detection module."""

import importlib
import os
import sys
from pathlib import Path

import pytest


def _get_real_project_module():
    """Get the real memory.project module, not a mock.

    Other test files may mock memory.project at module level, polluting
    sys.modules. This function ensures we get the real implementation.
    """
    # Remove any mocked version
    if "memory.project" in sys.modules:
        mod = sys.modules["memory.project"]
        # Check if it's a mock (mocks have _mock_name attribute)
        if hasattr(mod, "_mock_name") or str(type(mod).__name__) == "Mock":
            del sys.modules["memory.project"]

    # Import fresh
    import memory.project

    return importlib.reload(memory.project)


# Get the real module
_project_module = _get_real_project_module()
detect_project = _project_module.detect_project
normalize_project_name = _project_module.normalize_project_name
normalize_org_repo_slug = _project_module.normalize_org_repo_slug
get_project_hash = _project_module.get_project_hash


@pytest.fixture(autouse=True)
def clear_project_env():
    """Clear AI_MEMORY_PROJECT_ID env var before each test.

    detect_project() checks this env var first, so tests need it cleared
    to test directory-based detection.
    """
    old_value = os.environ.pop("AI_MEMORY_PROJECT_ID", None)
    yield
    if old_value is not None:
        os.environ["AI_MEMORY_PROJECT_ID"] = old_value


class TestNormalizeProjectName:
    """Test project name normalization."""

    def test_lowercase_conversion(self):
        """Project names should be converted to lowercase."""
        assert normalize_project_name("MyProject") == "myproject"
        assert normalize_project_name("UPPERCASE") == "uppercase"

    def test_spaces_to_hyphens(self):
        """Spaces should be converted to hyphens."""
        assert normalize_project_name("My Project") == "my-project"
        assert normalize_project_name("Multi Word Name") == "multi-word-name"

    def test_special_char_replacement(self):
        """Special characters should be converted to hyphens."""
        assert normalize_project_name("project_v2.0") == "project-v2-0"
        assert normalize_project_name("app@2024") == "app-2024"
        assert normalize_project_name("site#test") == "site-test"

    def test_hyphen_cleanup(self):
        """Leading/trailing hyphens should be removed."""
        assert normalize_project_name("-project-") == "project"
        assert normalize_project_name("--multiple--") == "multiple"

    def test_consecutive_hyphens(self):
        """Multiple consecutive hyphens should collapse to one."""
        assert normalize_project_name("my___project") == "my-project"
        assert normalize_project_name("test...app") == "test-app"

    def test_length_limit(self):
        """Names longer than 50 chars should be truncated."""
        long_name = "a" * 60
        result = normalize_project_name(long_name)
        assert len(result) == 50
        assert result == "a" * 50

    def test_empty_name_handling(self):
        """Empty or invalid names should return unnamed-project."""
        assert normalize_project_name("") == "unnamed-project"
        assert normalize_project_name("   ") == "unnamed-project"
        assert normalize_project_name("---") == "unnamed-project"

    @pytest.mark.parametrize(
        "input_name,expected",
        [
            ("my-app", "my-app"),
            ("MyApp", "myapp"),
            ("my_app", "my-app"),
            ("my.app", "my-app"),
            ("my app", "my-app"),
            ("MY-APP", "my-app"),
        ],
    )
    def test_normalization_examples(self, input_name, expected):
        """Test various normalization examples."""
        assert normalize_project_name(input_name) == expected


class TestNormalizeOrgRepoSlug:
    """Test owner/repo normalization while preserving slash separators."""

    def test_preserves_separator_and_normalizes_case(self):
        assert normalize_org_repo_slug("Axonify/Thunderball") == "axonify/thunderball"

    def test_returns_none_for_non_repo_values(self):
        assert normalize_org_repo_slug("plain-project") is None


class TestGetProjectHash:
    """Test project hash generation."""

    def test_hash_length(self, tmp_path):
        """Hash should be exactly 12 characters."""
        test_dir = tmp_path / "test-project"
        test_dir.mkdir()
        hash_result = get_project_hash(str(test_dir))
        assert len(hash_result) == 12

    def test_hash_deterministic(self, tmp_path):
        """Same path should always produce same hash."""
        test_dir = tmp_path / "test-project"
        test_dir.mkdir()
        hash1 = get_project_hash(str(test_dir))
        hash2 = get_project_hash(str(test_dir))
        assert hash1 == hash2

    def test_different_paths_different_hashes(self, tmp_path):
        """Different paths should produce different hashes."""
        dir1 = tmp_path / "project-a"
        dir2 = tmp_path / "project-b"
        dir1.mkdir()
        dir2.mkdir()
        hash1 = get_project_hash(str(dir1))
        hash2 = get_project_hash(str(dir2))
        assert hash1 != hash2

    def test_hash_format(self, tmp_path):
        """Hash should be lowercase hexadecimal."""
        test_dir = tmp_path / "test-project"
        test_dir.mkdir()
        hash_result = get_project_hash(str(test_dir))
        assert hash_result.isalnum()
        assert hash_result == hash_result.lower()


class TestDetectProject:
    """Test project detection from working directory."""

    def test_normal_project_raises_without_env_or_git(self, tmp_path):
        """PLAN-028 P1B / W-09 (DEC-PM302-D2 Q-5): basename fallback removed.

        Previously this test asserted the directory basename was returned;
        post-W-09 the call must raise ValueError because the cwd has no
        AI_MEMORY_PROJECT_ID, no git remote, and is not an edge-case sentinel.
        """
        project_dir = tmp_path / "my-app"
        project_dir.mkdir()
        with pytest.raises(ValueError, match="project detection failed"):
            detect_project(str(project_dir))

    def test_nested_project_raises_without_env_or_git(self, tmp_path):
        """Nested non-git directory raises post-W-09 (Q-5 strict-remove)."""
        nested = tmp_path / "home" / "user" / "work" / "webapp"
        nested.mkdir(parents=True)
        with pytest.raises(ValueError, match="project detection failed"):
            detect_project(str(nested))

    def test_env_var_directory_with_spaces_normalizes(self, tmp_path, monkeypatch):
        """AI_MEMORY_PROJECT_ID input gets normalized (spaces → hyphens)."""
        project_dir = tmp_path / "ignored-by-env-path"
        project_dir.mkdir()
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", "My Project")
        assert detect_project(str(project_dir)) == "my-project"

    def test_env_var_special_characters_normalize(self, tmp_path, monkeypatch):
        """AI_MEMORY_PROJECT_ID input gets normalized (dots/underscores)."""
        project_dir = tmp_path / "ignored-by-env-path"
        project_dir.mkdir()
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", "project_v2.0")
        assert detect_project(str(project_dir)) == "project-v2-0"

    def test_root_directory(self):
        """Root directory should return root-project."""
        result = detect_project("/")
        assert result == "root-project"

    def test_home_directory(self):
        """Home directory should return home-project."""
        home = os.path.expanduser("~")
        result = detect_project(home)
        assert result == "home-project"

    def test_tmp_directory(self, tmp_path):
        """Temp directories should return temp-project."""
        # Test /tmp path
        if Path("/tmp").exists():
            tmp_dir = Path("/tmp") / "build-12345"
            tmp_dir.mkdir(exist_ok=True)
            result = detect_project(str(tmp_dir))
            assert result == "temp-project"
            tmp_dir.rmdir()

    def test_var_tmp_directory(self, tmp_path):
        """Var temp directories should return temp-project."""
        if Path("/var/tmp").exists():
            # Create actual test directory to avoid non-existent path
            test_dir = Path("/var/tmp") / "test-build-12345"
            test_dir.mkdir(exist_ok=True)
            try:
                result = detect_project(str(test_dir))
                assert result == "temp-project"
            finally:
                test_dir.rmdir()

    def test_default_cwd_when_none_with_env(self, monkeypatch, tmp_path):
        """When cwd=None, falls back to os.getcwd(); env var still wins."""
        project_dir = tmp_path / "current-project"
        project_dir.mkdir()
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", "current-project")
        result = detect_project()
        assert result == "current-project"

    def test_env_project_id_owner_repo_preserves_slash(self, monkeypatch, tmp_path):
        """AI_MEMORY_PROJECT_ID keeps owner/repo form when provided."""
        project_dir = tmp_path / "ignored-project"
        project_dir.mkdir()
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", "Axonify/Thunderball")
        result = detect_project(str(project_dir))
        assert result == "axonify/thunderball"

    def test_symlink_path_raises_without_env_or_git(self, tmp_path):
        """Symlink resolution still happens, but final path raises post-W-09."""
        real_dir = tmp_path / "real-project"
        link_dir = tmp_path / "link-project"
        real_dir.mkdir()
        link_dir.symlink_to(real_dir)

        with pytest.raises(ValueError, match="project detection failed"):
            detect_project(str(link_dir))

    def test_deterministic_raise_on_repeated_calls(self, tmp_path):
        """Repeated calls with same un-resolvable cwd raise consistently."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        with pytest.raises(ValueError):
            detect_project(str(project_dir))
        with pytest.raises(ValueError):
            detect_project(str(project_dir))

    def test_invalid_path_raises(self):
        """Non-existent paths now raise ValueError (no silent basename fallback)."""
        with pytest.raises(ValueError, match="project detection failed"):
            detect_project("/nonexistent/path/to/project")

    def test_relative_path_raises_without_env(self, tmp_path, monkeypatch):
        """Relative paths resolve to absolute but still raise post-W-09."""
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ValueError, match="project detection failed"):
            detect_project("my-project")

    def test_path_with_dots_raises_without_env(self, tmp_path, monkeypatch):
        """Paths with .. resolve correctly but still raise post-W-09."""
        parent = tmp_path / "parent"
        child = parent / "child"
        child.mkdir(parents=True)

        monkeypatch.chdir(child)
        with pytest.raises(ValueError, match="project detection failed"):
            detect_project("..")

    def test_root_dir_still_sentinels(self):
        """Edge-case sentinels remain (Q-6 deferred as TD)."""
        # The "root-project" sentinel is preserved for now per Q-6.
        assert detect_project("/") == "root-project"

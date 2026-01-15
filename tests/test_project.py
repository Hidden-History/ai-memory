"""Tests for project detection module."""

import os
import pytest
from pathlib import Path

from memory.project import (
    detect_project,
    normalize_project_name,
    get_project_hash,
)


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

    @pytest.mark.parametrize("input_name,expected", [
        ("my-app", "my-app"),
        ("MyApp", "myapp"),
        ("my_app", "my-app"),
        ("my.app", "my-app"),
        ("my app", "my-app"),
        ("MY-APP", "my-app"),
    ])
    def test_normalization_examples(self, input_name, expected):
        """Test various normalization examples."""
        assert normalize_project_name(input_name) == expected


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
        assert hash_result.islower()


class TestDetectProject:
    """Test project detection from working directory."""

    def test_normal_project(self, tmp_path):
        """Normal project directories should use directory name."""
        project_dir = tmp_path / "my-app"
        project_dir.mkdir()
        result = detect_project(str(project_dir))
        assert result == "my-app"

    def test_nested_project(self, tmp_path):
        """Nested projects should use leaf directory name."""
        nested = tmp_path / "home" / "user" / "work" / "webapp"
        nested.mkdir(parents=True)
        result = detect_project(str(nested))
        assert result == "webapp"

    def test_space_in_name(self, tmp_path):
        """Directory names with spaces should be normalized."""
        project_dir = tmp_path / "My Project"
        project_dir.mkdir()
        result = detect_project(str(project_dir))
        assert result == "my-project"

    def test_special_characters(self, tmp_path):
        """Special characters should be normalized."""
        project_dir = tmp_path / "project_v2.0"
        project_dir.mkdir()
        result = detect_project(str(project_dir))
        assert result == "project-v2-0"

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

    def test_default_cwd_when_none(self, monkeypatch, tmp_path):
        """When cwd=None, should use os.getcwd()."""
        project_dir = tmp_path / "current-project"
        project_dir.mkdir()
        monkeypatch.chdir(project_dir)
        result = detect_project()
        assert result == "current-project"

    def test_symlink_resolution(self, tmp_path):
        """Symlinks should be resolved to actual path."""
        real_dir = tmp_path / "real-project"
        link_dir = tmp_path / "link-project"
        real_dir.mkdir()
        link_dir.symlink_to(real_dir)

        result = detect_project(str(link_dir))
        # Should resolve to the real directory name
        assert result == "real-project"

    def test_deterministic_results(self, tmp_path):
        """Same input should always produce same output."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        result1 = detect_project(str(project_dir))
        result2 = detect_project(str(project_dir))
        assert result1 == result2

    def test_invalid_path_handling(self):
        """Invalid (non-existent) paths should still extract directory name.

        Per implementation: Don't check path.exists() - Claude Code might pass
        paths that don't exist on filesystem (virtual paths, remote paths).
        """
        result = detect_project("/nonexistent/path/to/project")
        # Returns normalized directory name, not "unknown-project"
        assert result == "project"

    def test_relative_path_handling(self, tmp_path, monkeypatch):
        """Relative paths should be resolved to absolute."""
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        result = detect_project("my-project")
        assert result == "my-project"

    def test_path_with_dots(self, tmp_path, monkeypatch):
        """Paths with .. should be resolved correctly."""
        parent = tmp_path / "parent"
        child = parent / "child"
        child.mkdir(parents=True)

        monkeypatch.chdir(child)
        result = detect_project("..")
        assert result == "parent"

    @pytest.mark.parametrize("path,expected", [
        ("/home/user/projects/my-app", "my-app"),
        ("/home/user/work/client/webapp", "webapp"),
        ("/", "root-project"),
    ])
    def test_edge_case_examples(self, path, expected):
        """Test documented edge cases."""
        # Skip if path doesn't exist (except root)
        if path != "/" and not Path(path).exists():
            pytest.skip(f"Path {path} does not exist")

        result = detect_project(path)
        assert result == expected

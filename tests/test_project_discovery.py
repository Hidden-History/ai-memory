"""Tests for discover_projects() and ProjectSyncConfig (PLAN-009).

Tests:
1. Empty dir → {}
2. 1 YAML → 1 config
3. 3 YAMLs → all 3 configs
4. Malformed YAML → skipped (no crash)
5. Missing project_id → skipped
6. Legacy fallback: empty dir + GITHUB_REPO env var → 1 config
7. No fallback: dir has files, GITHUB_REPO env var is ignored
8. Default field values are correct
"""

import os
import textwrap
from pathlib import Path

import pytest

from memory.config import ProjectSyncConfig, discover_projects

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_yaml(directory: Path, filename: str, content: str) -> Path:
    """Write a YAML file into a temp directory."""
    path = directory / filename
    path.write_text(textwrap.dedent(content))
    return path


# ---------------------------------------------------------------------------
# Test 1: Empty directory returns empty dict
# ---------------------------------------------------------------------------


def test_empty_dir_returns_empty_dict(tmp_path: Path) -> None:
    projects_d = tmp_path / "projects.d"
    projects_d.mkdir()

    result = discover_projects(config_dir=projects_d)

    assert result == {}


# ---------------------------------------------------------------------------
# Test 2: Single YAML file → 1 ProjectSyncConfig
# ---------------------------------------------------------------------------


def test_single_yaml_returns_one_config(tmp_path: Path) -> None:
    projects_d = tmp_path / "projects.d"
    projects_d.mkdir()
    write_yaml(
        projects_d,
        "my-project.yaml",
        """
        project_id: "my-org/my-project"
        source_directory: "/home/user/repos/my-project"

        github:
          enabled: true
          repo: "my-org/my-project"
          branch: "develop"

        jira:
          enabled: false
        """,
    )

    result = discover_projects(config_dir=projects_d)

    assert len(result) == 1
    assert "my-org/my-project" in result
    cfg = result["my-org/my-project"]
    assert isinstance(cfg, ProjectSyncConfig)
    assert cfg.project_id == "my-org/my-project"
    assert cfg.github_repo == "my-org/my-project"
    assert cfg.github_branch == "develop"
    assert cfg.github_enabled is True
    assert cfg.jira_enabled is False
    assert cfg.source_directory == "/home/user/repos/my-project"


# ---------------------------------------------------------------------------
# Test 3: Three YAML files → 3 configs, all loaded
# ---------------------------------------------------------------------------


def test_three_yamls_returns_all_three(tmp_path: Path) -> None:
    projects_d = tmp_path / "projects.d"
    projects_d.mkdir()

    repos = [
        ("alpha.yaml", "alpha-org/alpha"),
        ("beta.yaml", "beta-org/beta"),
        ("gamma.yaml", "gamma-org/gamma"),
    ]
    for filename, repo in repos:
        write_yaml(
            projects_d,
            filename,
            f"""
            project_id: "{repo}"
            github:
              repo: "{repo}"
              branch: "main"
              enabled: true
            jira:
              enabled: false
            """,
        )

    result = discover_projects(config_dir=projects_d)

    assert len(result) == 3
    assert "alpha-org/alpha" in result
    assert "beta-org/beta" in result
    assert "gamma-org/gamma" in result


# ---------------------------------------------------------------------------
# Test 4: Malformed YAML is skipped, valid files still load
# ---------------------------------------------------------------------------


def test_malformed_yaml_is_skipped(tmp_path: Path) -> None:
    projects_d = tmp_path / "projects.d"
    projects_d.mkdir()

    # Valid file
    write_yaml(
        projects_d,
        "good.yaml",
        """
        project_id: "good-org/good"
        github:
          repo: "good-org/good"
          enabled: true
        jira:
          enabled: false
        """,
    )

    # Malformed YAML (invalid indentation / broken syntax)
    (projects_d / "broken.yaml").write_text(
        "project_id: broken\n  bad_indent: [unclosed"
    )

    result = discover_projects(config_dir=projects_d)

    assert len(result) == 1
    assert "good-org/good" in result


# ---------------------------------------------------------------------------
# Test 5: YAML missing project_id is skipped
# ---------------------------------------------------------------------------


def test_missing_project_id_is_skipped(tmp_path: Path) -> None:
    projects_d = tmp_path / "projects.d"
    projects_d.mkdir()

    # File with no project_id
    write_yaml(
        projects_d,
        "no-id.yaml",
        """
        github:
          repo: "some-org/some-repo"
          enabled: true
        jira:
          enabled: false
        """,
    )

    # Valid file
    write_yaml(
        projects_d,
        "valid.yaml",
        """
        project_id: "valid-org/valid"
        github:
          repo: "valid-org/valid"
          enabled: true
        jira:
          enabled: false
        """,
    )

    result = discover_projects(config_dir=projects_d)

    assert "valid-org/valid" in result
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Test 6: Legacy fallback — empty dir + GITHUB_REPO env var
# ---------------------------------------------------------------------------


def test_legacy_fallback_with_empty_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects_d = tmp_path / "projects.d"
    projects_d.mkdir()

    monkeypatch.setenv("GITHUB_REPO", "legacy-org/legacy-repo")

    result = discover_projects(config_dir=projects_d)

    assert len(result) == 1
    assert "legacy-org/legacy-repo" in result
    cfg = result["legacy-org/legacy-repo"]
    assert cfg.project_id == "legacy-org/legacy-repo"
    assert cfg.github_repo == "legacy-org/legacy-repo"


# ---------------------------------------------------------------------------
# Test 7: No fallback — dir has valid files, GITHUB_REPO env var is ignored
# ---------------------------------------------------------------------------


def test_no_fallback_when_dir_has_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects_d = tmp_path / "projects.d"
    projects_d.mkdir()

    write_yaml(
        projects_d,
        "registered.yaml",
        """
        project_id: "registered-org/registered"
        github:
          repo: "registered-org/registered"
          enabled: true
        jira:
          enabled: false
        """,
    )

    # Even though GITHUB_REPO is set, it should NOT appear in results
    monkeypatch.setenv("GITHUB_REPO", "should-not-appear/repo")

    result = discover_projects(config_dir=projects_d)

    assert len(result) == 1
    assert "registered-org/registered" in result
    assert "should-not-appear/repo" not in result


# ---------------------------------------------------------------------------
# Test 8: Default field values are correct
# ---------------------------------------------------------------------------


def test_default_field_values(tmp_path: Path) -> None:
    projects_d = tmp_path / "projects.d"
    projects_d.mkdir()

    # Minimal YAML — only project_id provided
    write_yaml(
        projects_d,
        "minimal.yaml",
        """
        project_id: "minimal-org/minimal"
        """,
    )

    result = discover_projects(config_dir=projects_d)

    assert "minimal-org/minimal" in result
    cfg = result["minimal-org/minimal"]

    # Check all defaults
    assert cfg.source_directory is None
    assert cfg.github_repo is None
    assert cfg.github_branch == "main"
    assert cfg.github_enabled is True
    assert cfg.jira_enabled is False
    assert cfg.jira_instance_url is None
    assert cfg.jira_projects == []


# ---------------------------------------------------------------------------
# Test 9: Non-existent directory returns empty dict (no crash)
# ---------------------------------------------------------------------------


def test_nonexistent_dir_returns_empty_dict(tmp_path: Path) -> None:
    projects_d = tmp_path / "projects.d" / "does_not_exist"
    # Do NOT create the directory

    result = discover_projects(config_dir=projects_d)

    assert result == {}


# ---------------------------------------------------------------------------
# Test 10: Legacy fallback not triggered when dir does not exist but env set
# ---------------------------------------------------------------------------


def test_legacy_fallback_when_dir_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects_d = tmp_path / "projects.d"
    # Do NOT create the directory

    monkeypatch.setenv("GITHUB_REPO", "fallback-org/fallback")

    result = discover_projects(config_dir=projects_d)

    assert len(result) == 1
    assert "fallback-org/fallback" in result


# ---------------------------------------------------------------------------
# Test 11: Jira fields are parsed correctly
# ---------------------------------------------------------------------------


def test_jira_fields_parsed(tmp_path: Path) -> None:
    projects_d = tmp_path / "projects.d"
    projects_d.mkdir()

    write_yaml(
        projects_d,
        "jira-project.yaml",
        """
        project_id: "jira-org/jira-project"
        github:
          repo: "jira-org/jira-project"
          enabled: true
          branch: "main"
        jira:
          enabled: true
          instance_url: "https://jira-org.atlassian.net"
          projects:
            - PROJ
            - DEV
            - OPS
        """,
    )

    result = discover_projects(config_dir=projects_d)

    assert "jira-org/jira-project" in result
    cfg = result["jira-org/jira-project"]
    assert cfg.jira_enabled is True
    assert cfg.jira_instance_url == "https://jira-org.atlassian.net"
    assert cfg.jira_projects == ["PROJ", "DEV", "OPS"]


# ---------------------------------------------------------------------------
# Test 12: ProjectSyncConfig dataclass field alias (ensure dataclass_field used)
# ---------------------------------------------------------------------------


def test_project_sync_config_dataclass_instantiation() -> None:
    cfg = ProjectSyncConfig(
        project_id="test/repo",
        github_repo="test/repo",
        github_branch="feature-branch",
        jira_projects=["A", "B"],
    )

    assert cfg.project_id == "test/repo"
    assert cfg.github_repo == "test/repo"
    assert cfg.github_branch == "feature-branch"
    assert cfg.jira_projects == ["A", "B"]

    # Verify that the default_factory works for jira_projects
    cfg2 = ProjectSyncConfig(project_id="test/repo2")
    assert cfg2.jira_projects == []
    # Ensure it's a new list, not shared
    cfg2.jira_projects.append("C")
    assert cfg.jira_projects == ["A", "B"]


# ---------------------------------------------------------------------------
# Test 13: AI_MEMORY_PROJECTS_DIR env var overrides Path.home() default
# (CRITICAL-1: Docker container fix — container home != /config)
# ---------------------------------------------------------------------------


def test_env_var_projects_dir_overrides_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AI_MEMORY_PROJECTS_DIR must take precedence over the Path.home() default
    so that the Docker-mounted /config/projects.d is used inside the container
    rather than the container user's home directory.
    """
    custom_dir = tmp_path / "custom-projects.d"
    custom_dir.mkdir()

    write_yaml(
        custom_dir,
        "docker-project.yaml",
        """
        project_id: "docker-org/docker-project"
        github:
          repo: "docker-org/docker-project"
          enabled: true
        jira:
          enabled: false
        """,
    )

    # Simulate container: env var points to the mounted path
    monkeypatch.setenv("AI_MEMORY_PROJECTS_DIR", str(custom_dir))

    # Call with no explicit config_dir — must use env var, not Path.home()
    result = discover_projects()

    assert len(result) == 1
    assert "docker-org/docker-project" in result


def test_explicit_config_dir_beats_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicit config_dir argument always wins over AI_MEMORY_PROJECTS_DIR."""
    env_dir = tmp_path / "env-projects.d"
    env_dir.mkdir()
    write_yaml(
        env_dir,
        "env-project.yaml",
        """
        project_id: "env-org/env-project"
        github:
          repo: "env-org/env-project"
          enabled: true
        jira:
          enabled: false
        """,
    )

    explicit_dir = tmp_path / "explicit-projects.d"
    explicit_dir.mkdir()
    write_yaml(
        explicit_dir,
        "explicit-project.yaml",
        """
        project_id: "explicit-org/explicit-project"
        github:
          repo: "explicit-org/explicit-project"
          enabled: true
        jira:
          enabled: false
        """,
    )

    monkeypatch.setenv("AI_MEMORY_PROJECTS_DIR", str(env_dir))

    # Explicit arg must override env var
    result = discover_projects(config_dir=explicit_dir)

    assert len(result) == 1
    assert "explicit-org/explicit-project" in result
    assert "env-org/env-project" not in result


# ---------------------------------------------------------------------------
# Test 15: Duplicate project_id across two YAML files — last file wins
# (MINOR-8: document and assert the defined behavior)
# ---------------------------------------------------------------------------


def test_duplicate_project_id_last_file_wins(tmp_path: Path) -> None:
    """When two YAML files declare the same project_id, the one that sorts
    later alphabetically wins.  This is expected/documented behavior: files
    are processed via ``sorted(...glob("*.yaml"))`` so the outcome is
    deterministic.  Operators who need to override a config can prefix their
    file name so it sorts after the original (e.g., ``z-override.yaml``).
    """
    projects_d = tmp_path / "projects.d"
    projects_d.mkdir()

    # "a-first.yaml" sorts before "b-second.yaml"
    write_yaml(
        projects_d,
        "a-first.yaml",
        """
        project_id: "shared-org/shared-repo"
        github:
          repo: "shared-org/shared-repo"
          branch: "old-branch"
          enabled: true
        jira:
          enabled: false
        """,
    )
    write_yaml(
        projects_d,
        "b-second.yaml",
        """
        project_id: "shared-org/shared-repo"
        github:
          repo: "shared-org/shared-repo"
          branch: "new-branch"
          enabled: true
        jira:
          enabled: false
        """,
    )

    result = discover_projects(config_dir=projects_d)

    # Only one entry for the shared project_id
    assert len(result) == 1
    assert "shared-org/shared-repo" in result

    # b-second.yaml sorted last, so its branch value wins
    cfg = result["shared-org/shared-repo"]
    assert (
        cfg.github_branch == "new-branch"
    ), "Last file alphabetically should win when project_id is duplicated"


# ---------------------------------------------------------------------------
# Test 16: OSError on unreadable file is logged as error, not warning
# (MAJOR-5: OSError split from data-format errors)
# ---------------------------------------------------------------------------


def test_oserror_on_unreadable_file_does_not_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreadable file (e.g. wrong permissions) must not crash
    discover_projects().  The remaining valid files are still loaded.
    """
    if os.getuid() == 0:
        pytest.skip("chmod-based tests require non-root execution")

    projects_d = tmp_path / "projects.d"
    projects_d.mkdir()

    # Valid file
    write_yaml(
        projects_d,
        "readable.yaml",
        """
        project_id: "readable-org/readable"
        github:
          repo: "readable-org/readable"
          enabled: true
        jira:
          enabled: false
        """,
    )

    # File that exists but cannot be read
    unreadable = projects_d / "unreadable.yaml"
    unreadable.write_text("project_id: unreadable\n")
    original_mode = unreadable.stat().st_mode
    unreadable.chmod(0o000)

    try:
        result = discover_projects(config_dir=projects_d)
        # The readable project must still be returned
        assert "readable-org/readable" in result
        # The unreadable one must not appear (and must not have crashed)
        assert "unreadable" not in result
    finally:
        # Restore permissions so tmp_path cleanup can delete the file
        unreadable.chmod(original_mode)


# ---------------------------------------------------------------------------
# Test 17: Empty string project_id is skipped
# ---------------------------------------------------------------------------


def test_empty_string_project_id_is_skipped(tmp_path: Path) -> None:
    """project_id: '' (empty string) must be skipped."""
    projects_d = tmp_path / "projects.d"
    projects_d.mkdir()
    write_yaml(projects_d, "empty-id.yaml", 'project_id: ""')
    result = discover_projects(config_dir=projects_d)
    assert result == {}


# ---------------------------------------------------------------------------
# Test 18: config_dir pointing to a file returns empty dict
# ---------------------------------------------------------------------------


def test_config_dir_is_file_returns_empty_dict(tmp_path: Path) -> None:
    """config_dir pointing to a file (not directory) returns {}."""
    not_a_dir = tmp_path / "projects.d"
    not_a_dir.write_text("I am a file")
    result = discover_projects(config_dir=not_a_dir)
    assert result == {}


# ---------------------------------------------------------------------------
# Test 19: GITHUB_REPO="" empty string must not trigger legacy fallback
# ---------------------------------------------------------------------------


def test_empty_github_repo_env_no_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GITHUB_REPO='' (empty string) must not trigger legacy fallback."""
    projects_d = tmp_path / "projects.d"
    projects_d.mkdir()
    monkeypatch.setenv("GITHUB_REPO", "")
    result = discover_projects(config_dir=projects_d)
    assert result == {}


# ---------------------------------------------------------------------------
# Test 20: Scalar jira.projects string coerced to list
# ---------------------------------------------------------------------------


def test_scalar_jira_projects_coerced_to_list(tmp_path: Path) -> None:
    """jira.projects: PROJ (scalar string) must be coerced to ['PROJ']."""
    projects_d = tmp_path / "projects.d"
    projects_d.mkdir()
    write_yaml(
        projects_d,
        "scalar-jira.yaml",
        """
        project_id: "scalar-org/scalar"
        jira:
          enabled: true
          instance_url: "https://scalar.atlassian.net"
          projects: PROJ
        """,
    )
    result = discover_projects(config_dir=projects_d)
    cfg = result["scalar-org/scalar"]
    assert cfg.jira_projects == ["PROJ"]
    assert isinstance(cfg.jira_projects, list)

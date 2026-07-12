"""Tests for memory.secrets_env — inline-search auth hardening (PR #270).

Covers:
- pin_qdrant_api_key restores the canonical key over a poisoned ambient one
  (secrets-first, unconditional override — the immunization the inline skill
  snippets rely on).
- is_auth_error detects the 401/auth text that search.py preserves in
  QdrantUnavailable("Search failed: {e}").
"""

from memory.secrets_env import _read_env_key, is_auth_error, pin_qdrant_api_key


def _write_secrets(install_dir, **keys):
    docker = install_dir / "docker"
    docker.mkdir(parents=True, exist_ok=True)
    secrets = docker / ".env.secrets"
    secrets.write_text("\n".join(f'{k}="{v}"' for k, v in keys.items()) + "\n")
    return secrets


class TestPinQdrantApiKey:
    def test_overrides_poisoned_ambient_key(self, tmp_path, monkeypatch):
        """A stale exported QDRANT_API_KEY is overridden by the .env.secrets value."""
        _write_secrets(tmp_path, QDRANT_API_KEY="canonical-secret")
        monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(tmp_path))
        monkeypatch.setenv("QDRANT_API_KEY", "deadbeef-wrong")

        assert pin_qdrant_api_key() is True
        import os

        assert os.environ["QDRANT_API_KEY"] == "canonical-secret"

    def test_falls_back_to_env_file(self, tmp_path, monkeypatch):
        """When .env.secrets lacks the key, docker/.env is used as fallback."""
        docker = tmp_path / "docker"
        docker.mkdir(parents=True)
        (docker / ".env").write_text('QDRANT_API_KEY="from-env-file"\n')
        monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(tmp_path))
        monkeypatch.setenv("QDRANT_API_KEY", "deadbeef-wrong")

        assert pin_qdrant_api_key() is True
        import os

        assert os.environ["QDRANT_API_KEY"] == "from-env-file"

    def test_returns_false_when_no_key_available(self, tmp_path, monkeypatch):
        """No secret files → nothing pinned, ambient value left untouched."""
        monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(tmp_path))
        monkeypatch.setenv("QDRANT_API_KEY", "ambient-unchanged")

        assert pin_qdrant_api_key() is False
        import os

        assert os.environ["QDRANT_API_KEY"] == "ambient-unchanged"

    def test_secrets_take_precedence_over_env(self, tmp_path, monkeypatch):
        """secrets-first: .env.secrets wins over docker/.env when both define the key."""
        docker = tmp_path / "docker"
        docker.mkdir(parents=True)
        (docker / ".env").write_text('QDRANT_API_KEY="from-env-file"\n')
        (docker / ".env.secrets").write_text('QDRANT_API_KEY="from-secrets"\n')
        monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(tmp_path))

        assert pin_qdrant_api_key() is True
        import os

        assert os.environ["QDRANT_API_KEY"] == "from-secrets"


class TestReadEnvKey:
    def test_strips_inline_trailing_comment(self, tmp_path):
        """A whitespace-preceded `# comment` is not part of the value."""
        env_path = tmp_path / ".env"
        env_path.write_text("QDRANT_API_KEY=abc123  # rotated 2026-01-01\n")

        assert _read_env_key(env_path, "QDRANT_API_KEY") == "abc123"

    def test_equals_in_value_unchanged(self, tmp_path):
        """Only the first `=` is a delimiter; `=` inside the value is preserved."""
        env_path = tmp_path / ".env"
        env_path.write_text("QDRANT_API_KEY=ab=c1=23\n")

        assert _read_env_key(env_path, "QDRANT_API_KEY") == "ab=c1=23"

    def test_hash_without_preceding_space_stays_in_value(self, tmp_path):
        """A `#` glued to the value (no preceding whitespace) is not a comment."""
        env_path = tmp_path / ".env"
        env_path.write_text("QDRANT_API_KEY=abc#123\n")

        assert _read_env_key(env_path, "QDRANT_API_KEY") == "abc#123"

    def test_quoted_value_still_unwrapped(self, tmp_path):
        """Surrounding quotes are stripped as before."""
        env_path = tmp_path / ".env"
        env_path.write_text('QDRANT_API_KEY="abc123"\n')

        assert _read_env_key(env_path, "QDRANT_API_KEY") == "abc123"

    def test_quoted_value_with_hash_not_truncated(self, tmp_path):
        """A `#` inside quotes is literal, not an inline comment."""
        env_path = tmp_path / ".env"
        env_path.write_text('QDRANT_API_KEY="abc # def"\n')

        assert _read_env_key(env_path, "QDRANT_API_KEY") == "abc # def"


class TestIsAuthError:
    def test_detects_wrapped_401(self):
        """The exact shape search.py raises: QdrantUnavailable('Search failed: {e}')."""
        assert is_auth_error("Search failed: Unexpected Response: 401 (Unauthorized)")

    def test_detects_variants(self):
        for msg in (
            "401 Unauthorized",
            "Invalid API key provided",
            "403 Forbidden",
            "UNAUTHORIZED",
        ):
            assert is_auth_error(msg), msg

    def test_ignores_non_auth_failures(self):
        for msg in (
            "No memories found matching your query",
            "Connection refused",
            "Search failed: timeout waiting for embedding service",
            "peer certificate forbidden by policy",
            "Request forbidden by administrative rules",
        ):
            assert not is_auth_error(msg), msg

    def test_ignores_embedded_digit_runs(self):
        """A 401/403 digit-run embedded in an unrelated number is not a match."""
        for msg in (
            "timeout after 1403ms",
            "collection has 4030 points",
            "connect to node4013 refused",
        ):
            assert not is_auth_error(msg), msg

    def test_detects_word_bounded_status_codes(self):
        for msg in (
            "Unexpected Response: 401 Unauthorized",
            "403 Forbidden",
        ):
            assert is_auth_error(msg), msg

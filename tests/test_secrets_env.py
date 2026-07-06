"""Tests for memory.secrets_env — inline-search auth hardening (PR #270).

Covers:
- pin_qdrant_api_key restores the canonical key over a poisoned ambient one
  (secrets-first, unconditional override — the immunization the inline skill
  snippets rely on).
- is_auth_error detects the 401/auth text that search.py preserves in
  QdrantUnavailable("Search failed: {e}").
"""

from memory.secrets_env import is_auth_error, pin_qdrant_api_key


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
        ):
            assert not is_auth_error(msg), msg

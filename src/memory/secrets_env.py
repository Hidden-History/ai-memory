"""Secrets-first env pinning for inline search callers (PR #270 hardening).

Inline skill snippets (aim-best-practices-researcher, aim-search) call
``search_memories()`` in-process rather than routing through
``scripts/memory/run-with-env.sh``. That leaves them exposed to a stale
exported ``QDRANT_API_KEY`` in the ambient shell: pydantic ``MemoryConfig``
gives an ambient env var priority over the ``.env.secrets`` file, so a
poisoned ambient key silently wins and search fails auth.

``pin_qdrant_api_key`` closes that gap by mirroring run-with-env.sh's
``load_env_var`` for the one key the search path uses (the main
``QDRANT_API_KEY`` — ``MemorySearch`` builds its client with
``read_only=False``): it reads the canonical value secrets-first and
*unconditionally* overrides ``os.environ`` before the config is built.

``is_auth_error`` detects the auth-failure text that ``search.py`` preserves
in ``QdrantUnavailable(f"Search failed: {e}")`` so callers can fail loud
instead of degrading to a false "no results" success.

Usage (inline snippet, before constructing the search):
    from memory.secrets_env import pin_qdrant_api_key, is_auth_error
    pin_qdrant_api_key()
    try:
        results = search_memories(...)
    except Exception as e:
        if is_auth_error(str(e)):
            print("❌ Memory search auth FAILED ...")
        raise
"""

import os
import re
from pathlib import Path

# Auth-failure phrase markers preserved in the wrapped QdrantUnavailable
# message, matched as a plain substring.
_AUTH_ERROR_MARKERS = ("unauthorized", "invalid api key")

# HTTP auth status codes; word-boundary matched so a digit-run embedded in an
# unrelated message (e.g. "timeout after 1403ms") doesn't false-positive.
_AUTH_ERROR_CODE_RE = re.compile(r"\b(?:401|403)\b")

# A dotenv inline comment requires whitespace before the `#`; a `#` glued to
# the value (no preceding whitespace) is part of the value, not a comment.
_INLINE_COMMENT_RE = re.compile(r"(?<=\s)#.*$")


def _read_env_key(env_path: Path, name: str) -> str | None:
    """Return the first non-empty value for ``name`` in ``env_path``, or None.

    Mirrors run-with-env.sh::load_env_var parsing: strip surrounding quotes,
    skip comments and empty placeholders.
    """
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        if key.strip() != name:
            continue
        val = val.strip()
        if val[:1] in ('"', "'"):
            # Quoted: the value is everything up to the matching close quote;
            # a `#` inside the quotes is literal, not a comment.
            quote = val[0]
            val = val[1:].partition(quote)[0]
        else:
            val = _INLINE_COMMENT_RE.sub("", val).strip()
        if val:
            return val
    return None


def pin_qdrant_api_key() -> bool:
    """Force ``QDRANT_API_KEY`` from the install's secret files into os.environ.

    Secrets-first (``docker/.env.secrets`` then ``docker/.env`` fallback),
    unconditional override — matches run-with-env.sh so inline callers get the
    canonical key regardless of a stale exported ``QDRANT_API_KEY``.

    Returns True if a value was pinned, False if none was found (ambient value,
    if any, is left untouched).
    """
    install_dir = Path(
        os.environ.get("AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory"))
    )
    for env_path in (
        install_dir / "docker" / ".env.secrets",
        install_dir / "docker" / ".env",
    ):
        value = _read_env_key(env_path, "QDRANT_API_KEY")
        if value:
            os.environ["QDRANT_API_KEY"] = value
            return True
    return False


def is_auth_error(msg: str) -> bool:
    """True if ``msg`` looks like a Qdrant authentication failure (401/403)."""
    lowered = msg.lower()
    if _AUTH_ERROR_CODE_RE.search(lowered):
        return True
    return any(marker in lowered for marker in _AUTH_ERROR_MARKERS)

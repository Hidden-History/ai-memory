"""Shared guard keeping the test suite off the operator's production datastore.

TD-881 / TD-876. One implementation, imported by both ``tests/conftest.py`` and
``tests/integration/conftest.py``, so the two levels cannot drift apart.

What this layer is, and is not
------------------------------
OS-level network-namespace isolation is the load-bearing protection: a run
wrapped in ``unshare -rn`` is *structurally* unable to reach a production
service, and that holds for the gRPC path, for HTTP, and for subprocesses,
because a namespace is inherited across ``fork``/``exec``.

This module is the configuration layer beneath it. It exists for the case a
namespace cannot cover: a developer typing a bare ``pytest tests/`` with no
wrapper. It makes the *default target* safe, and refuses a production target
outright unless the caller opts in deliberately.

It is not, and must not become, a connect-time guard. A previous design patched
``socket.connect`` and was blind to the production client's gRPC path, because
grpcio's C-core never enters Python's ``socket`` module -- it passed its own
plain-socket self-test while leaving production reachable. Anything claiming to
block connections must be validated by the tripwire accept-counter, never by a
self-test of its own construction.
"""

import os

import pytest

# Ports belonging to the operator's real services.
#
# The sources genuinely differ, so the set is written out rather than derived at
# runtime. The Qdrant/embedding/Langfuse ports are field defaults in
# src/memory/config.py, but the Qdrant *gRPC* port is a deployment value that
# lives only in docker/.env (QDRANT_GRPC_PORT) and appears nowhere in src/.
# Deriving from config alone would therefore have produced a set missing 26351 --
# the live gRPC port, and the one a socket-layer guard already failed to cover.
# 6334 is qdrant-client's own gRPC default, reachable whenever the env var is
# unset. tests/test_datastore_guard.py asserts this set stays in sync with the
# config defaults, so drift fails a test instead of silently weakening the guard.
PRODUCTION_PORTS = frozenset({26350, 26351, 28080, 23100, 6334})

# Escape hatch for a deliberate run against real services.
LIVE_OPT_IN_ENV = "AI_MEMORY_ALLOW_LIVE_DATASTORE"

# Where an un-targeted run points instead of production.
#
# Constraints this value has to satisfy, all of them learned the hard way:
#   * src/memory/config.py bounds qdrant_port to ge=1024, le=65535, so a
#     low-numbered sentinel such as 1 makes MemoryConfig raise a pydantic
#     ValidationError during collection rather than fail at connect time.
#   * It must sit outside /proc/sys/net/ipv4/ip_local_port_range (32768-60999
#     here) so the kernel can never auto-assign it to an unrelated process and
#     turn the sentinel into something that actually answers.
#   * An out-of-range port such as 99999 raises an opaque error from inside the
#     client, and an unresolvable hostname costs a DNS timeout per attempt.
# 65535 is the top of the valid range, above the ephemeral band, and reads
# unmistakably as "not a real service".
SENTINEL_HOST = "localhost"
SENTINEL_PORT = 65535
SENTINEL_URL = f"http://{SENTINEL_HOST}:{SENTINEL_PORT}"


def live_datastore_allowed(env=None):
    """Return True when the caller has deliberately opted in to real services."""
    env = os.environ if env is None else env
    return env.get(LIVE_OPT_IN_ENV, "").strip().lower() in {"1", "true", "yes"}


def port_from_url(url):
    """Return the port in ``url``, or None when it carries no explicit port."""
    if not url:
        return None
    _, _, tail = url.rpartition(":")
    digits = ""
    for char in tail:
        if char.isdigit():
            digits += char
        else:
            break
    return int(digits) if digits else None


# The variables that decide which Qdrant the fixtures build a client against.
# These, and only these, are what `qdrant_base_url` and `qdrant_client` consume,
# and they are the three mechanisms TD-881 enumerated.
QDRANT_TARGET_VARS = ("QDRANT_PORT", "QDRANT_URL")


def resolved_ports(env=None):
    """Return the Qdrant port(s) the suite is currently pointed at.

    Deliberately narrower than "every production port that appears anywhere in
    the environment", because that set cannot be kept clean from here.
    ``src/memory/classifier/config.py`` loads ``~/.ai-memory/docker/.env`` --
    the operator's *real install* -- straight into ``os.environ`` during
    collection, and unlike the rest of the suite it does not honour
    ``AI_MEMORY_INSTALL_DIR``, so the conftest's own isolation of that path does
    not reach it. That pulls EMBEDDING_PORT, QDRANT_GRPC_PORT and
    LANGFUSE_BASE_URL to their production values in every run. Refusing on those
    made 5889 tests error at setup while telling the operator nothing they could
    act on.

    Those ports are still *measured*: the tripwire binds all of them, so a
    connection to any one of them is counted and ratcheted. This function
    governs the refusal only, and the refusal governs the datastore that gets
    written to.

    The ordering that makes this safe: pytest_configure installs the sentinel
    before collection begins, and the loader above only fills keys that are
    *absent*, so it can never overwrite the Qdrant target.
    """
    env = os.environ if env is None else env
    ports = set()
    raw = env.get("QDRANT_PORT", "").strip()
    if raw.isdigit():
        ports.add(int(raw))
    port = port_from_url(env.get("QDRANT_URL"))
    if port is not None:
        ports.add(port)
    return ports


def install_safe_defaults(env=None):
    """Point an un-targeted run at the sentinel instead of production.

    An explicit target set by the caller is honoured and never overwritten --
    that is the whole point. The defect this replaces did the opposite: a
    session-scoped autouse fixture rewrote the caller's target to the live
    instance from *inside* the pytest process, after any pre-launch check had
    already passed, so no env-var mitigation could survive it.
    """
    env = os.environ if env is None else env
    env.setdefault("QDRANT_URL", SENTINEL_URL)
    env.setdefault("QDRANT_PORT", str(SENTINEL_PORT))


def assert_not_production(env=None):
    """Fail the run when it is pointed at a real service without an opt-in.

    Raises:
        pytest.UsageError: the effective target is a production port and
            ``AI_MEMORY_ALLOW_LIVE_DATASTORE`` is not set. UsageError rather
            than a bare exception so the refusal prints as a readable message
            instead of an INTERNALERROR traceback, and never as a skip -- a
            silently skipped safety check is indistinguishable from a passing
            one.
    """
    env = os.environ if env is None else env
    if live_datastore_allowed(env):
        return

    offending = sorted(resolved_ports(env) & PRODUCTION_PORTS)
    if not offending:
        return

    raise pytest.UsageError(
        f"Refusing to run: the test suite is pointed at Qdrant port(s) "
        f"{offending}, which belong to the operator's live install. A test run "
        "would read and write real memory data.\n"
        "\n"
        "An AI-Memory install exports QDRANT_PORT/QDRANT_URL into your shell, so "
        "this is the normal state on a maintainer machine -- it is what made "
        "the project's own verification command unsafe to run.\n"
        "\n"
        "Clear the target so the suite falls back to the sentinel, and run "
        "inside a network namespace so nothing can reach a real service even if "
        "something re-points it later:\n"
        "  env -u QDRANT_URL -u QDRANT_PORT \\\n"
        "    unshare -rn sh -c 'ip link set lo up && exec \"$@\"' _ \\\n"
        "      python3 -m pytest tests/\n"
        "\n"
        "The namespace does not clear environment variables, so both halves are "
        "needed: the env clears the target, the namespace enforces it.\n"
        f"To target real services on purpose, set {LIVE_OPT_IN_ENV}=1."
    )

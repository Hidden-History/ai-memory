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

What it does not cover
----------------------
Both entry points are pytest hooks in a conftest, so ``pytest --noconftest``
skips them and no refusal happens: 40 tests collect against a live target with
this module never imported. Nothing here can close that, because there is no
conftest left to close it from -- a mechanism surviving ``--noconftest`` would
have to live outside the test tree, in a ``-p`` plugin entry point or a
``sitecustomize``.

The exposure is contained today rather than blocked: files taking a live
fixture also import from ``conftest``, so under ``--noconftest`` they fail at
import instead of connecting. That is a property of how the suite happens to be
written, not a guarantee this module provides, and it is written down here
because the alternative is a docstring claiming protection that does not exist.
The namespace is what actually holds for every invocation.

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
#
# 6333 -- qdrant-client's REST default, the exact counterpart of 6334 -- is
# deliberately ABSENT, and the omission is load-bearing rather than an
# oversight. .github/workflows/test.yml runs its integration job against a
# Qdrant service container on 6333 and sets QDRANT_PORT: "6333"; adding it here
# would make the guard refuse that job on every run. 6333 is a CI service port
# in this repository, not an operator port, so refusing it would block a
# legitimate target while protecting nothing. The asymmetry with 6334 is real:
# 6334 is reached by accident when QDRANT_GRPC_PORT is unset, whereas 6333 is
# only ever reached deliberately. CI measured 6334 at the highest count of any
# port on the first green run, which is what settled it.
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

# Where a client lands when neither of those variables is set.
#
# Absence is not safety. MemoryConfig has no QDRANT_URL field at all, and its
# qdrant_port field default is this port -- the operator's live REST port -- so
# removing the variable does not leave the suite pointed nowhere. It leaves it
# pointed at production. On a normal install the same removal also uncovers
# ~/.ai-memory/docker/.env, which MemoryConfig reads through env_file and which
# names the same port, so both routes out of an empty environment arrive here.
#
# BP-197's rule is that a guard reading configuration can be defeated by
# anything that WRITES configuration. This is its removal-side twin: defeated by
# anything that DELETES configuration. Reproduced on a live install -- clearing
# QDRANT_PORT made resolved_ports() return an empty set and the refusal pass,
# while MemoryConfig resolved 26350. That is why an empty environment reports
# this port rather than an empty set: the guard has to answer "where would a
# client actually connect", not "what did the caller happen to type".
#
# tests/test_datastore_guard.py pins this to the field default, so a change to
# config.py fails a test instead of quietly moving the fallback.
CONFIG_FALLBACK_PORT = 26350


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

    An environment naming neither variable resolves to CONFIG_FALLBACK_PORT
    rather than to nothing -- see that constant for why an empty answer here was
    a false report of safety.
    """
    env = os.environ if env is None else env
    ports = set()
    raw = env.get("QDRANT_PORT", "").strip()
    if raw.isdigit():
        ports.add(int(raw))
    port = port_from_url(env.get("QDRANT_URL"))
    if port is not None:
        ports.add(port)
    if not ports:
        ports.add(CONFIG_FALLBACK_PORT)
    return ports


def install_safe_defaults(env=None):
    """Point an un-targeted run at the sentinel instead of production.

    An explicit target set by the caller is honoured and never overwritten --
    that is the whole point. The defect this replaces did the opposite: a
    session-scoped autouse fixture rewrote the caller's target to the live
    instance from *inside* the pytest process, after any pre-launch check had
    already passed, so no env-var mitigation could survive it.

    A caller that sets only one half of the pair gets the other half derived
    from it, never defaulted independently. Two independent ``setdefault`` calls
    produced a target that disagreed with itself: .github/workflows/test.yml's
    integration job sets only ``QDRANT_PORT: 6333``, so the port readers aimed at
    the CI service container while the URL readers -- ``wait_for_qdrant_healthy``
    among them -- aimed at the sentinel and polled it until it timed out.
    tests/integration/test_backup_restore_round_trip.py still carries a
    hand-rolled workaround for exactly that split.
    """
    env = os.environ if env is None else env
    url, port = env.get("QDRANT_URL"), env.get("QDRANT_PORT")
    if url and not port:
        derived = port_from_url(url)
        if derived is not None:
            env["QDRANT_PORT"] = str(derived)
    elif port and not url:
        host = env.get("QDRANT_HOST") or SENTINEL_HOST
        env["QDRANT_URL"] = f"http://{host}:{port}"
    elif not url and not port:
        env["QDRANT_URL"] = SENTINEL_URL
        env["QDRANT_PORT"] = str(SENTINEL_PORT)


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

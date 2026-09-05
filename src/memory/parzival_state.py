"""Cause-aware reading of the Parzival enablement record (SPEC-015 / AD-32).

The installer records three flat keys in ``$INSTALL_DIR/docker/.env``:
``PARZIVAL_ENABLED`` (value), ``PARZIVAL_ENABLED_CAUSE`` (cause) and
``PARZIVAL_ENABLED_CONDITION`` (condition). Consumers branch on the **cause**,
never on the bare value: "I chose not to" and "the installer could not" are
different states and need different operator advice.

Two rules live here because getting either wrong is silent:

* **Absent cause fails closed to "unknown".** A ``docker/.env`` carrying a bare
  ``PARZIVAL_ENABLED`` and no cause key is the normal state on every install
  predating this record — both ``.env.example`` merge loops append only *missing*
  keys, so nothing back-fills it. Reading that as ``opt-out`` would tell every
  operator whose install *failed* that they chose it.
* **The wording is stated once and rendered per host convention.** Consumers span
  bare CLI ``print()`` and markdown injected into a session as context; matching
  each site's ambient convention would yield different shapes for one semantic
  message, so the mapping lives here and callers pick a rendering.
"""

import os

CAUSE_OPT_OUT = "opt-out"
CAUSE_FAILED = "failed"
CAUSE_UNKNOWN = "unknown"

#: Causes the installer actually writes. "unknown" is a read-side sentinel only.
KNOWN_CAUSES = (CAUSE_OPT_OUT, CAUSE_FAILED)

# (plain, markdown) renderings of one semantic message per cause.
_MESSAGES = {
    CAUSE_OPT_OUT: (
        "Parzival is not enabled: it was declined at install. "
        "Re-run install.sh to install it.",
        "Parzival is not enabled: it was declined at install. "
        "Re-run `install.sh` to install it.",
    ),
    CAUSE_FAILED: (
        "Parzival is not enabled: it could not be installed. "
        "Enabling the flag will not fix this — re-run the installer to deploy "
        "the _ai-memory/ package.",
        "Parzival is not enabled: it could not be installed. "
        "Enabling the flag will not fix this — re-run the installer to deploy "
        "the `_ai-memory/` package.",
    ),
    CAUSE_UNKNOWN: (
        "Parzival is not enabled. This install did not record why; "
        "re-run the installer to record the cause.",
        "Parzival is not enabled. This install did not record why; "
        "re-run the installer to record the cause in `docker/.env`.",
    ),
}


def normalize_cause(raw) -> str:
    """Reduce a raw cause value to a known cause or ``unknown``.

    The single definition of the fail-closed rule. Its shell twins live at
    ``install.sh::normalize_parzival_cause`` and in ``upgrade.sh``'s Step 3.6 branch;
    shell cannot import Python, so ``tests/test_parzival_cause_equivalence.py``
    asserts one input table resolves identically through every copy.

    ``None`` means "no cause recorded" and is ``unknown``. A non-string is a
    **programming error and raises**: the value reaches here from a pydantic ``str``
    field, so the only way to get another type is a test double. That matters more
    than it looks — a ``MagicMock(spec=MemoryConfig)`` that never *assigns* the
    attribute still auto-creates a ``MagicMock`` for it, and ``spec=`` constrains
    attribute *names*, never their values. Under the old silent coercion that mock
    resolved to ``unknown``: the cause branches took the wrong path and the tests
    still passed. Raising converts that into a loud failure at the seam.
    """
    if raw is None:
        return CAUSE_UNKNOWN
    if not isinstance(raw, str):
        raise TypeError(
            "parzival cause must be a str (pydantic declares it as one); got "
            f"{type(raw).__name__}. A MagicMock here means a test double auto-created "
            "the attribute instead of assigning it -- spec= constrains names, not values."
        )
    # Order matches the shell twins exactly: strip CR (a CRLF .env), strip
    # whitespace, strip surrounding quotes, strip whitespace again, lowercase.
    # python-dotenv removes the CR and the quotes before MemoryConfig sees them, but
    # resolve_cause_from_env reads raw process env where neither has been stripped.
    cause = raw.rstrip("\r").strip().strip("\"'").strip().lower()
    return cause if cause in KNOWN_CAUSES else CAUSE_UNKNOWN


def resolve_cause(config) -> str:
    """Return the recorded cause, failing closed to ``unknown``.

    ``MemoryConfig`` sets ``env_ignore_empty=True``, so the installer's empty-cause
    write on the enabled path arrives as the field default rather than ``""``.

    The attribute is read directly rather than through ``getattr(..., "")``. A
    missing ``parzival_enabled_cause`` means the field was never declared on
    ``MemoryConfig`` -- ``extra="ignore"`` would then be silently discarding the key
    from ``docker/.env`` and every consumer would read ``unknown`` forever. That is a
    build defect, not an unrecorded cause, and swallowing it hid the difference.
    """
    return normalize_cause(config.parzival_enabled_cause)


def resolve_cause_from_env(environ=None) -> str:
    """Resolve the cause from raw process env — transport 2 (settings.json -> env).

    Host-side hooks read the record from the environment, not from ``docker/.env``
    (BUG-120), so they cannot go through ``MemoryConfig``. The fail-closed rule is
    the same one and lives here so it has a single definition.
    """
    env = os.environ if environ is None else environ
    return normalize_cause(env.get("PARZIVAL_ENABLED_CAUSE"))


def disabled_message(cause: str, *, markdown: bool = False) -> str:
    """Render the operator-facing 'not enabled' message for ``cause``.

    Set ``markdown=True`` for stdout that is injected into a session as context
    rather than read at a terminal.

    The argument is normalised rather than looked up as given. Callers that pass a
    raw config or env value instead of ``resolve_cause`` output would otherwise
    silently render the *unknown* message and lose the cause -- the failure is
    invisible because ``unknown`` is a legitimate rendering.
    """
    plain, rich = _MESSAGES[normalize_cause(cause)]
    return rich if markdown else plain

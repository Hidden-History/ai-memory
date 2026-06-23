#!/usr/bin/env python3
"""
aim-sot verify — 16-check verification gate for .sot/registry.yaml (BP-024).

Invoked via run-with-env.sh (Pattern B, BP-013): pyyaml is a venv dep.

Subcommands:
    run    Verify the committed registry (default) or a proposed patch
           (--proposal).  Emits a structured PASS / CONDITIONAL / FAIL verdict.

Flags (run):
    --registry PATH         Override registry path (skip git-root walk)
    --proposal PATH         JSON/YAML file with 'entries' key — gate a proposed
                            patch pre-apply instead of auditing the committed file
    --project-id ID         Explicit project_id for the 5a drift cache (skips
                            auto-resolution; use in CI or on resolution failure)
    --check-urls            Activate R2 URL resolution (default: no-op)
    --exec-drift-checks     Activate K3 drift_check execution (default: parse +
                            PATH-exists only; never run in trigger/propose paths)
    --json                  Machine-readable JSON output
    --strict                Exit non-zero (1) when the verdict is FAIL — for
                            CI/pre-commit gates. CONDITIONAL/PASS exit 0 even
                            with --strict.

Exit codes (default): 0 = all paths including FAIL verdicts (FAIL and
                CONDITIONAL exit 0 with the structured verdict on stdout; S3
                YAML-parse failure also exits 0 with a structured S3-FAIL
                verdict);
            1 = fatal system error (schema file unreadable, proposal file
                unreadable, etc.).
With --strict: a FAIL verdict (including an S3 YAML-parse FAIL) exits 1;
            PASS and CONDITIONAL still exit 0. Prefer this over parsing the
            default exit status — `verify run || exit 1` does NOT catch a FAIL.

Check taxonomy (BP-024):
    S1-S4  Schema & Structural Validity
    R1-R4  Referential Integrity
    C1-C4  Completeness & Coverage
    K1-K4  Content Correctness
"""

import argparse
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Sibling import — reuse detect_propose helpers (no copy-paste, no new module)
# ---------------------------------------------------------------------------

_DP_SCRIPT = Path(__file__).resolve().parent / "aim_sot_detect_propose.py"
_dp_spec = importlib.util.spec_from_file_location("aim_sot_detect_propose", _DP_SCRIPT)
_dp = importlib.util.module_from_spec(_dp_spec)
_dp_spec.loader.exec_module(_dp)

_find_registry = _dp._find_registry
_load_registry_entries = _dp._load_registry_entries
_project_root_from_registry = _dp._project_root_from_registry
_sha256_short = _dp._sha256_short
_read_drift_cache = _dp._read_drift_cache
_discover_candidates = _dp._discover_candidates
_filter_new_candidates = _dp._filter_new_candidates
_DRIFT_CACHE_DIR = _dp._DRIFT_CACHE_DIR

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "schema" / "registry.schema.json"
)

_CHECKS_ALL = [
    "S1",
    "S2",
    "S3",
    "S4",
    "R1",
    "R2",
    "R3",
    "R4",
    "C1",
    "C2",
    "C3",
    "C4",
    "K1",
    "K2",
    "K3",
    "K4",
]

_URL_FIELDS: frozenset[str] = frozenset(
    {"docs_url", "source_repo", "ci_url", "runbook_url", "dashboard_url", "api_spec"}
)

# Checks that are structurally inert with the current registry.schema.json — they
# never produce findings, so they must not be counted as substantively "passed"
# (BP-024 verdict integrity). See the inline notes on each check.
_NOOP_CHECKS: frozenset[str] = frozenset({"R3", "C2", "C4"})


def _drift_state_populated() -> bool:
    """True if the drift-state dir holds any sot_drift_*.json cache.

    A populated cache means a drift baseline likely exists even when
    _resolve_project_id fails for this project (baseline-loss / resolution
    failure), which K1 must surface as CONDITIONAL rather than silent PASS.
    """
    try:
        return any(_DRIFT_CACHE_DIR.glob("sot_drift_*.json"))
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Schema loading — S1/S4 driven from registry.schema.json (stdlib json, no dep)
# ---------------------------------------------------------------------------


def _load_schema_constraints() -> dict:
    """Load registry.schema.json and extract check-relevant constraints.

    Returns:
        entry_required: list[str]  — required entry fields
        entry_enums:    dict       — {field: [allowed_values]} for enum fields
        entry_str_fields: set[str] — fields typed as string (minLength >= 1)
    """
    try:
        schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"Error: cannot load registry schema at {_SCHEMA_PATH}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    entry_def = schema.get("definitions", {}).get("entry", {})
    props = entry_def.get("properties", {})

    entry_enums: dict[str, list] = {}
    entry_str_fields: set[str] = set()
    for field, field_def in props.items():
        if field_def.get("type") == "string":
            entry_str_fields.add(field)
        if "enum" in field_def:
            entry_enums[field] = field_def["enum"]

    return {
        "entry_required": entry_def.get("required", []),
        "entry_enums": entry_enums,
        "entry_str_fields": entry_str_fields,
    }


# ---------------------------------------------------------------------------
# Verdict building (BP-024 §2)
# ---------------------------------------------------------------------------


def _build_verdict(
    failures: list[dict],
    warnings: list[dict],
    checks_run: list[str],
) -> dict:
    """Build the structured verdict with distinct outcome buckets (BP-024 §2).

    Each check is classified into exactly one bucket, precedence
    fail > conditional > skipped-no-baseline > no-op > ran-pass:
      ran_pass  — substantive check that ran and produced zero findings.
      no_op     — structurally inert with the current schema (R3/C2/C4).
      skipped   — could not run because a drift baseline was unavailable
                  (K1 cold-start / baseline-loss / resolution failure).
    pass_count counts ONLY ran_pass so a human is not misled into reading a
    flat "N/16" as "content was verified" when K1 was skipped or a check is inert.
    """
    fail_checks = {f["check"] for f in failures}
    # Build cond_checks first from non-skipped warnings so that a check with both a
    # real conditional warning AND a skipped_no_baseline warning (mixed-baseline
    # registry — normal state) lands in cond, not skipped (DD-D). Precedence:
    # fail > conditional > skipped (FV-1).
    cond_checks = {
        w["check"] for w in warnings if w.get("kind") != "skipped_no_baseline"
    }
    skipped_checks = {
        w["check"] for w in warnings if w.get("kind") == "skipped_no_baseline"
    }
    # Subtract checks already classified into fail or cond. The - fail_checks term is
    # dead code for the current check taxonomy (no check emits both a hard FAIL and a
    # skipped_no_baseline warning) but is retained for forward-compatibility.
    skipped_checks = skipped_checks - fail_checks - cond_checks

    no_op = [
        c
        for c in checks_run
        if c in _NOOP_CHECKS
        and c not in fail_checks
        and c not in cond_checks
        and c not in skipped_checks
    ]
    ran_pass = [
        c
        for c in checks_run
        if c not in fail_checks
        and c not in cond_checks
        and c not in skipped_checks
        and c not in _NOOP_CHECKS
    ]

    fail_count = len(failures)
    if fail_count > 0:
        verdict = "FAIL"
    elif warnings:
        verdict = "CONDITIONAL"
    else:
        verdict = "PASS"

    return {
        "verdict": verdict,
        "checks_run": checks_run,
        "failures": failures,
        "warnings": warnings,
        "ran_pass": ran_pass,
        "no_op": no_op,
        "skipped": sorted(skipped_checks),
        "pass_count": len(ran_pass),
        "fail_count": fail_count,
    }


# ---------------------------------------------------------------------------
# Human-readable rendering
# ---------------------------------------------------------------------------


def _format_human(v: dict) -> str:
    verdict = v["verdict"]
    lines = [f"aim-sot verify: {verdict}"]

    if v["failures"]:
        lines.append(f"\nFailures ({v['fail_count']})")
        for f in v["failures"]:
            lines.append(f"  [{f['check']}] {f['entry_id']}: {f['detail']}")

    if v["warnings"]:
        lines.append(f"\nWarnings ({len(v['warnings'])})")
        for w in v["warnings"]:
            lines.append(f"  [{w['check']}] {w['entry_id']}: {w['detail']}")

    lines.append("")
    summary = f"Checks: {v['pass_count']} ran-pass"
    if v["no_op"]:
        summary += f", {len(v['no_op'])} no-op ({'/'.join(v['no_op'])})"
    if v["skipped"]:
        summary += (
            f", {len(v['skipped'])} skipped-no-baseline ({'/'.join(v['skipped'])})"
        )
    summary += f", {v['fail_count']} fail"
    lines.append(summary)

    lines.append("")
    if verdict == "PASS":
        lines.append("Registry is apply-eligible.")
    elif verdict == "CONDITIONAL":
        lines.append("Warnings require human review before apply.")
    else:
        lines.append("Registry has failures — apply blocked. Fix and re-run.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Finding constructors
# ---------------------------------------------------------------------------


def _fail(check: str, entry_id: str, detail: str) -> dict:
    return {"check": check, "entry_id": entry_id, "detail": detail}


def _warn(check: str, entry_id: str, detail: str) -> dict:
    return {"check": check, "entry_id": entry_id, "detail": detail}


# ---------------------------------------------------------------------------
# S1 — Schema compliance (required fields + type/minLength from schema)
# ---------------------------------------------------------------------------


def _check_S1(entries: list[dict], sc: dict) -> tuple[list[dict], list[dict]]:
    failures: list[dict] = []
    required = sc["entry_required"]
    str_fields = sc["entry_str_fields"]

    for entry in entries:
        eid = entry.get("id", "<missing>")
        for field in required:
            val = entry.get(field)
            if val is None:
                failures.append(_fail("S1", eid, f"Missing required field: {field}"))
            elif field in str_fields and not isinstance(val, str):
                failures.append(_fail("S1", eid, f"Field '{field}' must be a string"))
            elif field in str_fields and isinstance(val, str) and not val.strip():
                failures.append(_fail("S1", eid, f"Field '{field}' must be non-empty"))

    return failures, []


# ---------------------------------------------------------------------------
# S2 — ID uniqueness
# ---------------------------------------------------------------------------


def _check_S2(
    entries: list[dict],
    existing_ids: "set[str] | None" = None,
) -> tuple[list[dict], list[dict]]:
    """S2: no duplicate IDs.

    existing_ids: pre-seed the seen-set with committed registry IDs so a
    proposal whose id collides with an existing entry also fails (BP-024 S2).
    Audit mode passes None (no seed).
    """
    failures: list[dict] = []
    seen: set[str] = set(existing_ids or ())
    for entry in entries:
        eid = entry.get("id", "")
        if not eid:
            continue
        if eid in seen:
            failures.append(_fail("S2", eid, f"Duplicate id: {eid}"))
        else:
            seen.add(eid)
    return failures, []


# ---------------------------------------------------------------------------
# S4 — Controlled-vocabulary values (enums read from schema — no hardcoding)
# ---------------------------------------------------------------------------


def _check_S4(entries: list[dict], sc: dict) -> tuple[list[dict], list[dict]]:
    failures: list[dict] = []
    enums = sc["entry_enums"]

    for entry in entries:
        eid = entry.get("id", "<missing>")
        for field, allowed in enums.items():
            val = entry.get(field)
            if val is not None and val not in allowed:
                failures.append(
                    _fail(
                        "S4",
                        eid,
                        f"Unknown {field} value: '{val}' (allowed: {allowed})",
                    )
                )

    return failures, []


# ---------------------------------------------------------------------------
# R1 — File pointer resolves (exempt status=superseded)
# ---------------------------------------------------------------------------


def _check_R1(entries: list[dict], project_root: Path) -> tuple[list[dict], list[dict]]:
    """R1: sot_location must resolve on disk.

    Superseded entries are exempt — their sot_location may legitimately no
    longer exist (the forward pointer lives in docs_url / provenance_note).
    Missing-path + active/proposed is caught by C3.
    """
    failures: list[dict] = []
    for entry in entries:
        if entry.get("status") == "superseded":
            continue
        eid = entry.get("id", "<missing>")
        loc = entry.get("sot_location", "")
        if not loc:
            continue
        if not (project_root / loc).exists():
            failures.append(
                _fail(
                    "R1", eid, f"Path '{loc}' does not exist relative to project root"
                )
            )
    return failures, []


# ---------------------------------------------------------------------------
# R2 — URL resolves (no-op by default; --check-urls activates; never FAIL)
# ---------------------------------------------------------------------------


def _check_R2(
    entries: list[dict],
    check_urls: bool,
    *,
    _urlopen=None,
) -> tuple[list[dict], list[dict]]:
    """R2: URL resolution.

    Default (check_urls=False): no-op — no warnings, no verdict effect.
    A real registry almost always has URL fields; penalising their mere presence
    offline would make PASS permanently unreachable (wb-approved ruling).

    With --check-urls: attempt HEAD on each URL field; non-200 or timeout →
    warning (CONDITIONAL). Never hard-FAIL on network.
    """
    if not check_urls:
        return [], []

    warnings: list[dict] = []
    urlopen = _urlopen or urllib.request.urlopen

    for entry in entries:
        eid = entry.get("id", "<missing>")
        urls: list[str] = []

        for field in _URL_FIELDS:
            v = entry.get(field)
            if v and isinstance(v, str) and v.startswith(("http://", "https://")):
                urls.append(v)

        for link in entry.get("links") or []:
            if isinstance(link, dict):
                u = link.get("url", "")
                if u and isinstance(u, str) and u.startswith(("http://", "https://")):
                    urls.append(u)

        for url in urls:
            try:
                req = urllib.request.Request(url, method="HEAD")
                with urlopen(req, timeout=10) as resp:
                    if resp.status >= 400:
                        warnings.append(
                            _warn("R2", eid, f"URL returned {resp.status}: {url}")
                        )
            except Exception as exc:
                warnings.append(_warn("R2", eid, f"URL unreachable: {url} ({exc})"))

    return [], warnings


# ---------------------------------------------------------------------------
# R3 — Cross-reference consistency (always PASS with current schema)
# ---------------------------------------------------------------------------

# The current registry.schema.json v1 has no first-class entry-ID referencing
# fields (links[].url is a URL, not an entry ID). R3 is a no-op and returns
# PASS. It activates automatically if a future schema version adds
# cross-reference fields (e.g. "superseded_by", "related_to").


# ---------------------------------------------------------------------------
# R4 — Owner reference valid (roster-checked; @-normalized + casefolded)
# ---------------------------------------------------------------------------


def _extract_codeowners_handles(codeowners_path: Path) -> set[str]:
    """Extract all @handle tokens from CODEOWNERS, normalized (no @, casefolded)."""
    try:
        text = codeowners_path.read_text(encoding="utf-8")
    except OSError:
        return set()
    handles: set[str] = set()
    for token in re.findall(r"@[\w/.-]+", text):
        handles.add(token.lstrip("@").casefold())
    return handles


def _check_R4(entries: list[dict], project_root: Path) -> tuple[list[dict], list[dict]]:
    """R4: owner validated against CODEOWNERS when present.

    Normalization (wb-approved): strip leading @ and casefold both sides before
    comparing entry.owner to CODEOWNERS tokens (owner may be "@alice" or "alice").
    Mismatch → warning (CONDITIONAL), never FAIL.
    When no CODEOWNERS exists → silent no-op (same class as R2 offline / empty
    CODEOWNERS). PASS must be reachable for projects without a roster file.
    """
    warnings: list[dict] = []
    codeowners = project_root / "CODEOWNERS"

    if not codeowners.exists():
        return [], []  # no roster → no-op; PASS is reachable without CODEOWNERS

    known_handles = _extract_codeowners_handles(codeowners)

    for entry in entries:
        eid = entry.get("id", "<missing>")
        owner = entry.get("owner", "")
        if not owner:
            continue
        normalized = owner.lstrip("@").casefold()
        if known_handles and normalized not in known_handles:
            warnings.append(
                _warn("R4", eid, f"Owner '{owner}' not found in CODEOWNERS")
            )

    return [], warnings


# ---------------------------------------------------------------------------
# C1 — New components registered (CONDITIONAL/warning — not FAIL)
# ---------------------------------------------------------------------------


def _check_C1(
    entries: list[dict], discovered: list[dict]
) -> tuple[list[dict], list[dict]]:
    """C1: unregistered discovered components → warning (CONDITIONAL).

    Registration is user-discretionary (BP-029 propose-don't-mandate).
    Hard-failing on any unregistered dir makes the gate unusable on a partial
    registry. Use detect-propose to review and register candidates.
    """
    unregistered = _filter_new_candidates(discovered, entries)
    if not unregistered:
        return [], []

    locs = [c["sot_location"] for c in unregistered]
    shown = locs[:5]
    suffix = " …" if len(locs) > 5 else ""
    detail = (
        f"{len(unregistered)} discovered component(s) not registered: "
        f"{', '.join(shown)}{suffix}. Run detect-propose to review."
    )
    return [], [_warn("C1", "<registry>", detail)]


# C2 — No orphan entries (always PASS: audit mode has no removals; detect-propose
#       output only adds entries — kind=drift or new_candidate, never removes).
#       Activates if a future proposal format introduces explicit removals.

# C4 — N/A: registry.schema.json declares no top-level count field.
#       Activates if the schema later adds a declared-count assertion.


# ---------------------------------------------------------------------------
# C3 — Deprecated entries marked (missing path + not superseded → FAIL)
# ---------------------------------------------------------------------------

# NOTE: R1 and C3 both fire when an active entry's path is missing.
# This is intentional (BP-024): R1 = referential pointer broken (fix the path);
# C3 = entry is stale but not marked superseded (fix the status). They are
# distinct taxonomy rows requiring different remediation. Do not merge them.


def _check_C3(entries: list[dict], project_root: Path) -> tuple[list[dict], list[dict]]:
    failures: list[dict] = []
    for entry in entries:
        eid = entry.get("id", "<missing>")
        loc = entry.get("sot_location", "")
        status = entry.get("status", "")
        if not loc or status == "superseded":
            continue
        if not (project_root / loc).exists():
            failures.append(
                _fail(
                    "C3",
                    eid,
                    f"Path '{loc}' missing but status is '{status or '(none)'}'; "
                    "set status='superseded' or fix sot_location",
                )
            )
    return failures, []


# ---------------------------------------------------------------------------
# K1 — Description matches artifact (mandatory hash-trigger, not semantic)
# ---------------------------------------------------------------------------


def _check_K1(
    entries: list[dict],
    project_root: Path,
    cache: dict,
    *,
    project_id_resolved: bool = True,
    cache_populated: bool = False,
) -> tuple[list[dict], list[dict]]:
    """K1: content-hash drift vs the 5a baseline (spec §5; mandatory trigger).

    Deterministic trigger only — no token overlap, semantic heuristic, or regex.
    Only file sot_locations carry a content hash; directory paths are no-ops.

    A missing baseline is NOT a silent PASS. When a file-typed entry has no
    usable baseline — cold-start (no cache record / drift_status=='unverified'),
    baseline-loss, or a resolution failure (project_id unresolvable while a cache
    exists) — K1 emits a 'skipped_no_baseline' CONDITIONAL warning ("manual human
    confirmation required") so the verdict never reads as content-verified when it
    was not. project_id_resolved / cache_populated come from cmd_run.
    """
    warnings: list[dict] = []
    components = cache.get("components", {})

    for entry in entries:
        eid = entry.get("id", "")
        if not eid:
            continue
        loc = entry.get("sot_location", "")
        if not loc:
            continue
        full = project_root / loc
        if not full.is_file():
            continue  # directory sot_locations: no content-hash drift (spec §5 literal)

        # Resolution failure: cannot key into the drift cache for this project.
        if not project_id_resolved:
            if cache_populated:
                detail = (
                    "drift baseline unavailable: project_id could not be resolved "
                    "while a drift cache exists (baseline-loss); pass --project-id to "
                    "resolve — manual human confirmation required"
                )
            else:
                detail = (
                    "baseline unavailable: no drift cache has been built yet "
                    "(cold-start) — manual human confirmation required"
                )
            warnings.append({**_warn("K1", eid, detail), "kind": "skipped_no_baseline"})
            continue

        comp = components.get(eid)
        cached_sha = (comp or {}).get("last_verified_sha", "")
        drift_status = (comp or {}).get("drift_status", "")

        if comp is None or drift_status == "unverified" or not cached_sha:
            if comp is None:
                detail = (
                    "baseline unavailable: no drift baseline recorded for this entry "
                    "(baseline-loss)"
                    if components  # this project's cache, not the global dir-wide glob
                    else "baseline unavailable: no drift cache has been built yet "
                    "(cold-start)"
                ) + " — manual human confirmation required"
            elif drift_status == "unverified":
                detail = (
                    "baseline unverified: the machine has never confirmed this entry's "
                    "content (cold-start) — manual human confirmation required"
                )
            else:
                detail = (
                    "baseline unavailable: no recorded content hash for this entry — "
                    "manual human confirmation required"
                )
            warnings.append({**_warn("K1", eid, detail), "kind": "skipped_no_baseline"})
            continue

        current_sha = _sha256_short(full)
        if current_sha is None:
            warnings.append(
                _warn(
                    "K1",
                    eid,
                    "artifact unreadable: file exists but could not be hashed — "
                    "manual human confirmation required",
                )
            )
        elif current_sha != cached_sha:
            warnings.append(
                _warn(
                    "K1",
                    eid,
                    f"Content hash changed (was {cached_sha}, now {current_sha}); "
                    "description needs human re-confirmation",
                )
            )

    return [], warnings


# ---------------------------------------------------------------------------
# K2 — Date fields plausible (handles YAML-native datetime.date)
# ---------------------------------------------------------------------------


def _check_K2(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """K2: last_verified is a valid, non-future, non-epoch date.

    str(raw).strip() converts a YAML-native datetime.date object to "2026-06-01"
    before parsing — this is the class that blocked Item 3 (unquoted YAML date).
    """
    failures: list[dict] = []
    today = datetime.now(timezone.utc).date()
    epoch = date(1970, 1, 1)

    for entry in entries:
        eid = entry.get("id", "<missing>")
        raw = entry.get("last_verified")
        if raw is None:
            continue

        try:
            raw_str = str(raw).strip()
            if not raw_str:
                continue
            iso_str = (
                (raw_str + "T00:00:00+00:00")
                if len(raw_str) == 10
                else raw_str.replace("Z", "+00:00")
            )
            lv_dt = datetime.fromisoformat(iso_str)
            if lv_dt.tzinfo is None:
                lv_dt = lv_dt.replace(tzinfo=timezone.utc)
            lv_date = lv_dt.date()
        except (ValueError, TypeError, AttributeError):
            failures.append(
                _fail(
                    "K2",
                    eid,
                    f"last_verified is not a valid ISO-8601 date: {raw!r}",
                )
            )
            continue

        if lv_date > today:
            failures.append(
                _fail("K2", eid, f"last_verified is in the future: {lv_date}")
            )
        elif lv_date == epoch:
            failures.append(
                _fail("K2", eid, "last_verified is the epoch default (1970-01-01)")
            )

    return failures, []


# ---------------------------------------------------------------------------
# K3 — Drift-check command executable (parse-only by default; never execute)
# ---------------------------------------------------------------------------


def _check_K3(
    entries: list[dict],
    exec_drift_checks: bool,
) -> tuple[list[dict], list[dict]]:
    """K3: drift_check is a parseable command with binary on PATH.

    Security: parse-only by default (shlex + shutil.which); never execute.
    Execution only under --exec-drift-checks opt-in.

    IMPORTANT: K3 verifies executability only — it must NOT interpret a
    drift_check's exit code as registry validity. A non-zero exit from
    --exec-drift-checks is CONDITIONAL (not FAIL); the check is about whether
    the command CAN run, not what the drift outcome is.
    """
    failures: list[dict] = []
    warnings: list[dict] = []

    for entry in entries:
        eid = entry.get("id", "<missing>")
        dc = entry.get("drift_check")
        if not dc or not isinstance(dc, str):
            continue

        try:
            tokens = shlex.split(dc)
        except ValueError as exc:
            failures.append(_fail("K3", eid, f"drift_check syntax error: {exc}"))
            continue

        if not tokens:
            continue

        binary = tokens[0]
        if shutil.which(binary) is None:
            warnings.append(_warn("K3", eid, f"Binary '{binary}' not found on PATH"))
            continue  # skip execution attempt if binary absent

        if exec_drift_checks:
            try:
                result = subprocess.run(
                    tokens,
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode != 0:
                    warnings.append(
                        _warn(
                            "K3",
                            eid,
                            f"drift_check exited {result.returncode} "
                            "(executability check only — exit code does not "
                            "reflect registry validity)",
                        )
                    )
            except subprocess.TimeoutExpired:
                warnings.append(_warn("K3", eid, "drift_check timed out after 10s"))
            except OSError as exc:
                warnings.append(_warn("K3", eid, f"drift_check execution error: {exc}"))

    return failures, warnings


# ---------------------------------------------------------------------------
# K4 — No sot_location collision
# ---------------------------------------------------------------------------


def _check_K4(
    entries: list[dict],
    existing_locs: "dict[str, str] | None" = None,
) -> tuple[list[dict], list[dict]]:
    """K4: no two entries claim the same sot_location.

    existing_locs: pre-seed the seen-map with {sot_location: committed_id} so a
    proposed entry whose location collides with a committed entry's location also
    fails (BP-024 K4), symmetric with _check_S2's existing_ids. Audit mode passes
    None (intra-entry dedup only).
    """
    failures: list[dict] = []
    seen: dict[str, str] = dict(existing_locs or {})

    for entry in entries:
        eid = entry.get("id", "<missing>")
        loc = entry.get("sot_location", "")
        if not loc:
            continue
        if loc in seen:
            failures.append(
                _fail(
                    "K4",
                    eid,
                    f"sot_location '{loc}' already claimed by entry '{seen[loc]}'",
                )
            )
        else:
            seen[loc] = eid

    return failures, []


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def _run_all_checks(
    entries: list[dict],
    project_root: Path,
    cache: dict,
    sc: dict,
    check_urls: bool,
    exec_drift_checks: bool,
    *,
    _urlopen=None,
    existing_ids: "set[str] | None" = None,
    existing_locs: "dict[str, str] | None" = None,
    project_id_resolved: bool = True,
    cache_populated: bool = False,
    discover: bool = True,
) -> tuple[list[dict], list[dict]]:
    """Run checks S1-S4 / R1-R4 / C1-C4 / K1-K4.

    S3 is handled in cmd_run (YAML parse); R3/C2/C4 are no-ops with the
    current schema (see inline notes on each check).
    existing_ids / existing_locs: committed registry IDs / locations to seed S2
    and K4 in proposal mode (BP-024).
    project_id_resolved / cache_populated: K1 baseline-availability context.
    discover: when False, C1 auto-discovery is skipped (empty discovered list) —
    set for a non-conforming flat --registry root so verify matches
    detect-propose's M5 skip-discovery contract instead of scanning the
    registry's directory and emitting spurious C1 warnings.
    Returns (failures, warnings).
    """
    failures: list[dict] = []
    warnings: list[dict] = []

    # S1 / S2 / S4  (S3 = YAML parse, done in cmd_run)
    f, w = _check_S1(entries, sc)
    failures.extend(f)
    warnings.extend(w)
    f, w = _check_S2(entries, existing_ids)
    failures.extend(f)
    warnings.extend(w)
    f, w = _check_S4(entries, sc)
    failures.extend(f)
    warnings.extend(w)

    # R1 / R2 / R3 (no-op) / R4
    f, w = _check_R1(entries, project_root)
    failures.extend(f)
    warnings.extend(w)
    f, w = _check_R2(entries, check_urls, _urlopen=_urlopen)
    failures.extend(f)
    warnings.extend(w)
    # R3: no-op — no ID cross-ref fields in current schema
    f, w = _check_R4(entries, project_root)
    failures.extend(f)
    warnings.extend(w)

    # C1 / C2 (no-op) / C3 / C4 (no-op)
    discovered = _discover_candidates(project_root) if discover else []
    f, w = _check_C1(entries, discovered)
    failures.extend(f)
    warnings.extend(w)
    # C2: no-op — audit mode has no removals; propose-only format adds only
    f, w = _check_C3(entries, project_root)
    failures.extend(f)
    warnings.extend(w)
    # C4: no-op — schema has no declared-count field

    # K1 / K2 / K3 / K4
    f, w = _check_K1(
        entries,
        project_root,
        cache,
        project_id_resolved=project_id_resolved,
        cache_populated=cache_populated,
    )
    failures.extend(f)
    warnings.extend(w)
    f, w = _check_K2(entries)
    failures.extend(f)
    warnings.extend(w)
    f, w = _check_K3(entries, exec_drift_checks)
    failures.extend(f)
    warnings.extend(w)
    f, w = _check_K4(entries, existing_locs)
    failures.extend(f)
    warnings.extend(w)

    return failures, warnings


# ---------------------------------------------------------------------------
# Proposal loading (--proposal mode)
# ---------------------------------------------------------------------------


def _load_proposal(proposal_path: Path) -> tuple[list[dict], int]:
    """Load proposed entries from a JSON or YAML proposal file.

    Expected format: {"entries": [...]} — fully-formed proposed registry entry
    dicts ready for verification before apply.
    Returns (entries, exit_code); ec=1 on error.
    """
    try:
        text = proposal_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Error: cannot read proposal file: {exc}", file=sys.stderr)
        return [], 1

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            print(
                f"Error: proposal file is not valid JSON or YAML: {exc}",
                file=sys.stderr,
            )
            return [], 1

    if not isinstance(data, dict):
        print(
            "Error: proposal file must be a mapping with an 'entries' key",
            file=sys.stderr,
        )
        return [], 1

    # A wrong-shape proposal (a mapping lacking the 'entries' key) must be flagged
    # explicitly rather than verified as an empty entry set — verifying [] yields a
    # spurious pass-on-nothing that hides the malformed input (A2).
    if "entries" not in data:
        print(
            "Error: proposal file lacks an 'entries' key "
            '(expected {"entries": [...]})',
            file=sys.stderr,
        )
        return [], 1

    entries = data["entries"]
    if not isinstance(entries, list):
        print("Error: proposal 'entries' must be a list", file=sys.stderr)
        return [], 1

    return [e for e in entries if isinstance(e, dict)], 0


# ---------------------------------------------------------------------------
# Project ID resolution (for K1 cache load)
# ---------------------------------------------------------------------------


def _resolve_project_id(registry_path: Path) -> str | None:
    """Resolve project_id from the memory stack. Returns None on failure."""
    try:
        _install = os.environ.get(
            "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
        )
        _src = os.path.join(_install, "src")
        if _src not in sys.path:
            sys.path.insert(0, _src)
        from memory.project import resolve_project_id  # type: ignore[import]

        return resolve_project_id(cwd=str(registry_path.parent.parent))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace, *, _urlopen=None) -> int:
    strict = getattr(args, "strict", False)
    sc = _load_schema_constraints()

    # --- Resolve registry ---
    registry_path = _find_registry(getattr(args, "registry", None))
    if registry_path is None or not registry_path.exists():
        loc = f" at {registry_path}" if registry_path else ""
        print(f"No registry found{loc}. Run aim-sot detect-propose to create one.")
        return 0

    # --- S3: YAML parse (before any other check) ---
    try:
        entries, ec = _load_registry_entries(registry_path)
        if ec != 0:
            s3_fail = _fail("S3", "<registry>", "Registry YAML could not be parsed")
            v = _build_verdict([s3_fail], [], ["S3"])
            _emit_result(v, getattr(args, "as_json", False))
            return _verdict_exit_code(v, strict)
    except Exception as exc:
        s3_fail = _fail("S3", "<registry>", f"Registry YAML could not be parsed: {exc}")
        v = _build_verdict([s3_fail], [], ["S3"])
        _emit_result(v, getattr(args, "as_json", False))
        return _verdict_exit_code(v, strict)

    # --- Proposal mode: use proposed entries instead of committed registry ---
    proposal_path = getattr(args, "proposal", None)
    if proposal_path is not None:
        verify_entries, ec = _load_proposal(Path(proposal_path))
        if ec != 0:
            return 1
        # Seed S2/K4 with committed IDs/locations so proposed entries can't
        # collide with a committed entry (BP-024 S2/K4).
        existing_ids: set[str] | None = {
            e.get("id", "") for e in entries if e.get("id")
        }
        existing_locs: dict[str, str] | None = {
            e["sot_location"]: e.get("id", "<committed>")
            for e in entries
            if e.get("sot_location")
        }
    else:
        verify_entries = entries
        existing_ids = None
        existing_locs = None

    # --- Project root ---
    # A conforming registry (<root>/.sot/registry.yaml) yields a project root we
    # can safely scan; a flat --registry override yields None — resolve declared
    # locations relative to the registry's directory so a validation gate emits a
    # verdict rather than tracebacking on the None root.
    project_root = _project_root_from_registry(registry_path)
    resolve_root = project_root if project_root is not None else registry_path.parent

    # --- K1: load 5a drift cache. A missing baseline surfaces CONDITIONAL (not a
    #     silent PASS); --project-id lets CI/teammates supply the id explicitly. ---
    project_id = getattr(args, "project_id", None) or _resolve_project_id(registry_path)
    cache = _read_drift_cache(project_id) if project_id else {"components": {}}
    cache_populated = _drift_state_populated()
    project_id_resolved = project_id is not None
    if not project_id_resolved and cache_populated:
        print(
            "Warning: project_id could not be resolved but a drift cache exists; "
            "K1 content checks reported CONDITIONAL (baseline-loss). Pass "
            "--project-id to supply it explicitly.",
            file=sys.stderr,
        )

    # --- Run all 16 checks ---
    failures, warnings = _run_all_checks(
        verify_entries,
        resolve_root,
        cache,
        sc,
        check_urls=getattr(args, "check_urls", False),
        exec_drift_checks=getattr(args, "exec_drift_checks", False),
        _urlopen=_urlopen,
        existing_ids=existing_ids,
        existing_locs=existing_locs,
        project_id_resolved=project_id_resolved,
        cache_populated=cache_populated,
        discover=project_root is not None,
    )

    # --- S3 was checked above and passed; include it in the full verdict ---
    v = _build_verdict(failures, warnings, _CHECKS_ALL)
    _emit_result(v, getattr(args, "as_json", False))
    return _verdict_exit_code(v, strict)


def _emit_result(v: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(v, indent=2))
    else:
        print(_format_human(v))


def _verdict_exit_code(v: dict, strict: bool) -> int:
    """Exit code for a verdict (OBS-SOT-1).

    Default (strict=False): always 0 — the verdict is on stdout, exit status is
    not an outcome signal.  With --strict: 1 when verdict==FAIL, else 0 (a
    CONDITIONAL still exits 0 so a warning-only registry does not break a gate).
    """
    return 1 if (strict and v.get("verdict") == "FAIL") else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aim_sot_verify",
        description=(
            "16-check verification gate for .sot/registry.yaml (BP-024). "
            "Emits a structured PASS / CONDITIONAL / FAIL verdict."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Verify the registry or a proposed patch")
    run_p.add_argument(
        "--registry",
        metavar="PATH",
        help="Explicit path to registry.yaml (skips git-root walk)",
    )
    run_p.add_argument(
        "--proposal",
        metavar="PATH",
        help="JSON/YAML file with 'entries' key — gate a proposed patch pre-apply",
    )
    run_p.add_argument(
        "--project-id",
        metavar="ID",
        dest="project_id",
        help="Explicit project_id for the 5a drift cache (skips auto-resolution; "
        "use in CI or when auto-resolution fails)",
    )
    run_p.add_argument(
        "--check-urls",
        action="store_true",
        dest="check_urls",
        help="Activate R2 URL resolution (default: no-op)",
    )
    run_p.add_argument(
        "--exec-drift-checks",
        action="store_true",
        dest="exec_drift_checks",
        help="Activate K3 drift_check execution (default: parse + PATH-exists only)",
    )
    run_p.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Machine-readable JSON output",
    )
    run_p.add_argument(
        "--strict",
        action="store_true",
        dest="strict",
        help="Exit non-zero (1) when the verdict is FAIL — for CI/pre-commit "
        "gates (default: always exit 0; CONDITIONAL/PASS exit 0 even with "
        "--strict)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
